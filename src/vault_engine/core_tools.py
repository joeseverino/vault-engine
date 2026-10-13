"""Generic core tools: the engine's read/write/task surface across vaults.

register_core(mcp, vaults) registers each core tool once on a FastMCP instance.
Every tool takes a ``vault`` argument naming one configured vault; the call runs
against that vault's GovernanceContext (config, schema profile, loader), so the
sensitivity gate and schema validation stay per vault.
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, cast

from . import (
    daily_notes,
    task_service,
    vault_query_service,
    vault_search_service,
    vault_write_service,
)
from .context import GovernanceContext
from .search import tokenize
from .secret_unlock import (
    SecretUnlockResult,
    audit_secret_unlock,
    load_unlock_hash,
    prompt_unlock_phrase,
    verify_unlock_phrase,
)
from .sections import resolve_section
from .sensitivity import Sensitivity, advisory, body_is_releasable
from .tabular import is_separator as _is_table_separator
from .tabular import split_row as _split_table_row
from .vault import Doc, Index, _normalize_alias
from .vault_query_service import doc_to_hit as _hit_to_dict

QUICK_INDEX_DOC_ID = "report-playbook-mcp-index"
QUICK_INDEX_RESOURCE_TEMPLATE = "vault://{vault}/quick-index"
DOC_RESOURCE_TEMPLATE_URI = "vault://{vault}/doc/{doc_id}"

_Tool = TypeVar("_Tool", bound=Callable[..., Any])


class _McpServer(Protocol):
    def tool(self) -> Callable[[_Tool], _Tool]: ...

    def resource(
        self, uri: str, *, name: str, title: str, description: str, mime_type: str
    ) -> Callable[[_Tool], _Tool]: ...


FindMode = Literal["relevance", "system", "project", "text"]
TaskAction = Literal["add", "status", "promote", "delete"]

_SECRET_UNLOCK_MESSAGES = {
    "not_requested": (
        "Body withheld. To request release, rerun with include_restricted=True; "
        "the local MCP will still require an interactive unlock on the Mac."
    ),
    "disabled": (
        "Interactive unlock is disabled. Set SVMC_ALLOW_RESTRICTED_UNLOCK=1 "
        "in the local MCP environment to allow local unlock prompts."
    ),
    "no_unlock_hash": (
        "No local unlock hash is configured. Store a salted sha256 unlock hash "
        "in Keychain, SVMC_RESTRICTED_UNLOCK_HASH_FILE, or "
        "SVMC_RESTRICTED_UNLOCK_HASH."
    ),
    "prompt_unavailable": "Local hidden-input prompt was unavailable or cancelled.",
    "failed": "Local unlock phrase verification failed.",
}


# ----- per-vault helpers -------------------------------------------------------


def _wiki_targets(text: str) -> list[str]:
    targets: list[str] = []
    for part in text.split("[[")[1:]:
        target = part.split("]]", 1)[0].split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            targets.append(target)
    return targets


def _doc_for_reference(idx: Index, reference: str) -> Doc | None:
    clean = reference.strip().strip("`")
    if not clean:
        return None
    if clean in idx.by_doc_id:
        return idx.by_doc_id[clean]
    targets = _wiki_targets(reference) or [clean]
    by_title = {doc.title.lower(): doc for doc in idx.docs}
    by_path_stem = {doc.path.stem.lower(): doc for doc in idx.docs}
    for target in targets:
        lowered = target.lower()
        if lowered in by_title:
            return by_title[lowered]
        if lowered in by_path_stem:
            return by_path_stem[lowered]
    return None


def _quick_index_matches(idx: Index, query: str, *, limit: int = 3) -> list[dict[str, Any]]:
    """High-signal Quick Index table rows matching the query (a routing hint)."""
    quick_index_doc = idx.by_doc_id.get(QUICK_INDEX_DOC_ID)
    if quick_index_doc is None:
        return []
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    rows: list[dict[str, Any]] = []
    headers: list[str] | None = None
    for raw in quick_index_doc.body.splitlines():
        line = raw.strip()
        if not line.startswith("|") or not line.endswith("|"):
            headers = None
            continue
        cells = _split_table_row(line)
        if _is_table_separator(cells):
            continue
        if headers is None:
            headers = cells
            continue
        if len(cells) != len(headers):
            continue

        row = dict(zip(headers, cells, strict=True))
        intent = row.get("Intent") or row.get("Symptom") or row.get("Topic") or ""
        command = row.get("Command") or row.get("First step") or row.get("Start Here") or ""
        doc_ref = row.get("Doc") or row.get("Then Read") or ""
        score = (
            5 * len(query_tokens & tokenize(intent))
            + 3 * len(query_tokens & tokenize(command))
            + 2 * len(query_tokens & tokenize(doc_ref))
        )
        if score == 0:
            continue

        target_doc = _doc_for_reference(idx, doc_ref) or _doc_for_reference(idx, command)
        match: dict[str, Any] = {
            "score": score,
            "intent": intent,
            "command": command,
            "doc": doc_ref,
            "quick_index_doc_id": quick_index_doc.doc_id,
        }
        if target_doc is not None:
            match["target_doc_id"] = target_doc.doc_id
            match["target_title"] = target_doc.title
        rows.append(match)

    rows.sort(key=lambda item: (item["score"], item["intent"]), reverse=True)
    return rows[:limit]


def _find_relevance(name: str, ctx: GovernanceContext, query: str, limit: int) -> dict[str, Any]:
    response = vault_search_service.find_sections(ctx.loader, query, limit=limit)
    top_doc_id = response["hits"][0]["doc_id"] if response["hits"] else None
    matches = _quick_index_matches(ctx.loader.index(), query)
    if matches:
        response["quick_index_matches"] = matches
        if top_doc_id is None or matches[0].get("target_doc_id") == top_doc_id:
            response["recommended"] = {
                "source": QUICK_INDEX_RESOURCE_TEMPLATE.format(vault=name),
                **matches[0],
            }
    return response


def _find_system(ctx: GovernanceContext, query: str) -> dict[str, Any]:
    needle = query.strip().lower()
    if not needle:
        return {"query": query, "match_count": 0, "hits": []}
    matches = [
        d
        for d in ctx.loader.index().docs
        if needle in d.system.lower() or needle in d.title.lower() or needle in d.doc_id.lower()
    ]
    matches.sort(key=lambda d: (d.status != "active", d.last_reviewed or "", d.title))
    return {"query": query, "match_count": len(matches), "hits": [_hit_to_dict(d) for d in matches]}


def _find_project(ctx: GovernanceContext, query: str) -> dict[str, Any]:
    slug = query.strip()
    if not slug:
        return {"query": query, "match_count": 0, "hits": []}
    matches = [d for d in ctx.loader.index().docs if slug in d.related_projects]
    matches.sort(key=lambda d: (d.doc_type, d.title))
    return {"query": query, "match_count": len(matches), "hits": [_hit_to_dict(d) for d in matches]}


def _lookup_doc(
    ctx: GovernanceContext, identifier: str
) -> tuple[Doc | None, dict[str, str] | None]:
    """Resolve a stable doc_id, then a configured alias, then an exact title/path."""
    idx = ctx.loader.index()
    doc = idx.by_doc_id.get(identifier)
    if doc is not None:
        return doc, None

    alias = _normalize_alias(identifier)
    alias_doc_id = idx.aliases.get(alias)
    if alias_doc_id:
        return idx.by_doc_id[alias_doc_id], {
            "input": identifier,
            "matched_alias": alias,
            "target_doc_id": alias_doc_id,
        }
    if not alias:
        return None, None

    for candidate in idx.docs:
        names = {
            candidate.doc_id,
            candidate.title,
            candidate.relative_path,
            Path(candidate.relative_path).stem,
        }
        if alias in {_normalize_alias(n) for n in names}:
            return candidate, {
                "input": identifier,
                "matched_alias": candidate.title,
                "target_doc_id": candidate.doc_id,
                "source": "title_or_path",
            }
    return None, None


def _not_found_response(ctx: GovernanceContext, identifier: str) -> dict[str, Any]:
    duplicates = ctx.loader.index().duplicate_doc_ids.get(identifier)
    if duplicates:
        return {
            "doc_id": identifier,
            "found": False,
            "ambiguous": True,
            "error": f"duplicate doc_id {identifier!r}",
            "paths": duplicates,
            "guidance": "Resolve the duplicate frontmatter IDs before reading this document.",
        }
    return {
        "doc_id": identifier,
        "found": False,
        "guidance": "Call `find` to get a doc_id, then retry `read_doc` with it.",
        "alias_hint": (
            "For recurring local phrases, add an entry to the vault aliases "
            "file configured by `SVMC_ALIASES_PATH` or `[aliases].path`."
        ),
    }


def _withheld_response(base: dict[str, Any], result: str | None = None) -> dict[str, Any]:
    base["body_released"] = False
    base["advisory"] = advisory(Sensitivity.parse(str(base["sensitivity"])))
    if result:
        base["unlock"] = {
            "allowed": False,
            "result": result,
            "message": _SECRET_UNLOCK_MESSAGES[result],
        }
    return base


def _secret_adjacent_unlock(ctx: GovernanceContext, doc_id: str, title: str) -> SecretUnlockResult:
    config = ctx.config
    if not config.allow_secret_adjacent_unlock:
        return SecretUnlockResult(False, "disabled", _SECRET_UNLOCK_MESSAGES["disabled"])
    unlock_hash = load_unlock_hash(
        env_hash=config.secret_unlock_hash,
        hash_file=config.secret_unlock_hash_file,
        keychain_service=config.secret_unlock_keychain_service,
        keychain_account=config.secret_unlock_keychain_account,
    )
    if not unlock_hash:
        return SecretUnlockResult(
            False, "no_unlock_hash", _SECRET_UNLOCK_MESSAGES["no_unlock_hash"]
        )
    phrase = prompt_unlock_phrase(doc_id, title)
    if phrase is None:
        return SecretUnlockResult(
            False, "prompt_unavailable", _SECRET_UNLOCK_MESSAGES["prompt_unavailable"]
        )
    if not verify_unlock_phrase(phrase, unlock_hash):
        return SecretUnlockResult(False, "failed", _SECRET_UNLOCK_MESSAGES["failed"])
    return SecretUnlockResult(True, "released", "Local unlock succeeded for this request only.")


def _narrow_to_section(base: dict[str, Any], doc: Doc, section: str) -> dict[str, Any]:
    """Replace base['body'] with one section span. Runs only after the gate released it."""
    sec = resolve_section(doc.sections, section)
    if sec is None:
        base.pop("body", None)
        base["body_released"] = False
        base["section_error"] = f"no section {section!r} in {doc.doc_id}"
        base["available_sections"] = [
            {"section": s.slug, "heading_path": s.heading_path} for s in doc.sections
        ]
        return base
    base["body"] = sec.body
    base["heading"] = sec.heading or doc.title
    base["section"] = sec.slug
    base["heading_path"] = sec.heading_path
    base["body_scope"] = "section"
    return base


def _read_doc(
    ctx: GovernanceContext,
    doc_id: str,
    section: str | None,
    include_restricted: bool,
) -> dict[str, Any]:
    doc, resolved_from_alias = _lookup_doc(ctx, doc_id)
    if doc is None:
        return _not_found_response(ctx, doc_id)

    base: dict[str, Any] = {"doc_id": doc.doc_id, "found": True, **_hit_to_dict(doc)}
    if resolved_from_alias:
        base["resolved_from_alias"] = resolved_from_alias

    if doc.sensitivity is Sensitivity.SECRET_ADJACENT:
        if not include_restricted:
            return _withheld_response(base, "not_requested")
        unlock = _secret_adjacent_unlock(ctx, doc.doc_id, doc.title)
        audit_secret_unlock(
            ctx.config.secret_unlock_audit_log, doc_id=doc.doc_id, result=unlock.result
        )
        base["unlock"] = unlock.to_dict()
        if not unlock.allowed:
            return _withheld_response(base, unlock.result)
        base["body"] = doc.body
        base["body_released"] = True
        base["override_used"] = True
        base["advisory"] = advisory(doc.sensitivity, override_used=True)
        return _narrow_to_section(base, doc, section) if section else base

    if not body_is_releasable(doc.sensitivity, include_secret_adjacent=include_restricted):
        base["body_released"] = False
        base["advisory"] = advisory(doc.sensitivity)
        return base
    base["body"] = doc.body
    base["body_released"] = True
    if doc.sensitivity is Sensitivity.SENSITIVE:
        base["advisory"] = advisory(doc.sensitivity)
    return _narrow_to_section(base, doc, section) if section else base


def _render_doc_resource(ctx: GovernanceContext, doc_id: str) -> str:
    """A markdown resource view of one vault doc, gated like read_doc without unlock."""
    idx = ctx.loader.index()
    doc = idx.by_doc_id.get(doc_id)
    if doc is None:
        duplicates = idx.duplicate_doc_ids.get(doc_id)
        if duplicates:
            paths = "\n".join(f"- `{path}`" for path in duplicates)
            return (
                "# Duplicate Vault Doc ID\n\n"
                f"`{doc_id}` is used by multiple indexed documents:\n\n{paths}\n"
            )
        return f"# Vault Doc Not Found\n\nNo indexed doc has doc_id `{doc_id}`. Use `find`."
    if not body_is_releasable(doc.sensitivity, include_secret_adjacent=False):
        return (
            f"# {doc.title}\n\n"
            f"{advisory(doc.sensitivity)}\n\n"
            f"- doc_id: `{doc.doc_id}`\n"
            f"- path: `{doc.relative_path}`\n"
            f"- system: `{doc.system}`\n"
            f"- sensitivity: `{doc.sensitivity.value}`\n"
        )
    return doc.body


def _task_write(
    ctx: GovernanceContext,
    action: str,
    *,
    title: str | None,
    project: str | None,
    related_projects: list[str] | None,
    effort: str,
    priority: str,
    tags: list[str] | None,
    problem: str | None,
    fix: str | None,
    principle: str | None,
    source: str | None,
    doc_id: str | None,
    status: str | None,
    note_path: str | None,
) -> dict[str, Any]:
    loader = ctx.loader

    def missing(**required: str | None) -> dict[str, Any]:
        absent = [name for name, value in required.items() if not value]
        return {"ok": False, "error": f"action {action!r} requires {', '.join(absent)}"}

    if action == "add":
        if not title:
            return missing(title=title)
        return task_service.add_task(
            loader,
            title=title,
            project=project,
            related_projects=related_projects,
            effort=effort,
            priority=priority,
            tags=tags,
            problem=problem,
            fix=fix,
            principle=principle,
            source=source,
        )
    if action == "status":
        if not doc_id or not status:
            return missing(doc_id=doc_id, status=status)
        return task_service.set_task_status(loader, doc_id, status)
    if action == "promote":
        if not note_path or not title:
            return missing(note_path=note_path, title=title)
        return task_service.promote_note(
            loader, note_path, title=title, project=project, effort=effort, priority=priority
        )
    if action == "delete":
        if not doc_id:
            return missing(doc_id=doc_id)
        return task_service.delete_task(loader, doc_id)
    return {"ok": False, "error": f"unknown action {action!r}; one of add, status, promote, delete"}


# ----- registration ------------------------------------------------------------


def register_core(
    mcp: Any,
    vaults: Mapping[str, GovernanceContext],
    *,
    default: str | None = None,
) -> None:
    """Register the core tools and resources once, routed by a ``vault`` argument."""
    if not vaults:
        raise ValueError("register_core needs at least one vault")
    names = tuple(vaults)
    default_vault = default if default is not None else names[0]
    if default_vault not in vaults:
        raise ValueError(f"default vault {default_vault!r} is not one of {list(names)}")
    VaultName = Literal[names]  # type: ignore[valid-type]  # the vault names are only known at runtime
    server = cast("_McpServer", mcp)

    def ctx_for(vault: str) -> GovernanceContext:
        try:
            return vaults[vault]
        except KeyError:
            raise ValueError(f"unknown vault {vault!r}; one of {list(names)}") from None

    def tool(fn: _Tool) -> _Tool:
        fn.__annotations__["vault"] = VaultName
        return server.tool()(fn)

    # ----- resources -----------------------------------------------------------

    @server.resource(
        QUICK_INDEX_RESOURCE_TEMPLATE,
        name="quick-index",
        title="Vault Quick Index",
        description="A vault's navigation hub for broad 'how do I' or 'where do I look' questions.",
        mime_type="text/markdown",
    )
    def quick_index(vault: str) -> str:
        """Return a vault's Quick Index markdown."""
        return _render_doc_resource(ctx_for(vault), QUICK_INDEX_DOC_ID)

    @server.resource(
        DOC_RESOURCE_TEMPLATE_URI,
        name="vault-doc",
        title="Vault doc by doc_id",
        description="One indexed doc's markdown body, or an advisory plus metadata when restricted.",
        mime_type="text/markdown",
    )
    def vault_doc(vault: str, doc_id: str) -> str:
        """Return one indexed vault doc."""
        return _render_doc_resource(ctx_for(vault), doc_id)

    # ----- read tools ----------------------------------------------------------

    @tool
    def find(
        query: str,
        vault: str = default_vault,
        by: FindMode = "relevance",
        limit: int = 10,
        context_lines: int = 1,
        case_sensitive: bool = False,
    ) -> dict[str, Any]:
        """Find docs in a vault. Use this first for any question the vault may answer.

        Returns `match_count` and `hits` (each with a doc_id) in every mode. Then
        call `read_doc` on the best hit and answer from the doc's own text.

        Args:
            query: What to look for.
            vault: Which vault to search.
            by: relevance (ranked title/system/tag/section match, the default),
                system (docs whose system, title or doc_id contains the query),
                project (docs listing the query in related_projects), or
                text (ripgrep over doc bodies; hits carry line snippets, and
                restricted bodies are never searched).
            limit: Maximum hits (documents for `text`).
            context_lines: Lines of context per match, `text` only.
            case_sensitive: Case-sensitive match, `text` only.
        """
        ctx = ctx_for(vault)
        if by == "relevance":
            response = _find_relevance(vault, ctx, query, limit)
            response["match_count"] = len(response["hits"])
        elif by == "system":
            response = _find_system(ctx, query)
        elif by == "project":
            response = _find_project(ctx, query)
        elif by == "text":
            response = vault_query_service.search_body(
                ctx.loader,
                query,
                limit=limit,
                context_lines=context_lines,
                case_sensitive=case_sensitive,
            )
            if "error" not in response:
                response["hits"] = response.pop("hits_by_doc")
                response["match_count"] = response.pop("doc_count")
        else:
            return {
                "ok": False,
                "error": f"unknown mode {by!r}; one of relevance, system, project, text",
            }
        return {"vault": vault, "mode": by, **response}

    @tool
    def read_doc(
        doc_id: str,
        vault: str = default_vault,
        section: str | None = None,
        include_restricted: bool = False,
    ) -> dict[str, Any]:
        """Read a vault doc's markdown body, gated by its sensitivity.

        public, internal and sensitive bodies are released (sensitive ones carry an
        `advisory` to pass along). restricted bodies are withheld unless
        `include_restricted=True` and the local unlock on the Mac succeeds.

        Args:
            doc_id: The doc's stable id from a `find` hit (exact titles and
                vault-relative paths also resolve).
            vault: Which vault the doc lives in.
            section: A section slug or heading path from a `find` hit, to return
                just that section.
            include_restricted: Request a restricted body; local policy still decides.
        """
        return {"vault": vault, **_read_doc(ctx_for(vault), doc_id, section, include_restricted)}

    @tool
    def recent_changes(
        vault: str = default_vault, days: int = 7, limit: int = 50
    ) -> dict[str, Any]:
        """Recent commits touching a vault's indexed folders (metadata only, no diffs).

        Args:
            vault: Which vault.
            days: Look-back window in days.
            limit: Maximum commits.
        """
        return vault_query_service.recent_changes(ctx_for(vault).loader, days, limit)

    @tool
    def daily_progress(
        query: str, vault: str = default_vault, today: str | None = None
    ) -> dict[str, Any]:
        """Read the daily note a progress question refers to ("what did I do Friday?").

        Resolves today, yesterday, weekday names, `last Friday`, `YYYY-MM-DD` and
        `MM/DD/YYYY`, and returns the note body plus its progress lines.

        Args:
            query: The natural-language progress question.
            vault: Which vault's daily notes.
            today: ISO anchor date for relative terms; omit in normal use.
        """
        return daily_notes.daily_progress(ctx_for(vault).loader, query, today=today)

    # ----- write tools ---------------------------------------------------------

    @tool
    def set_frontmatter(
        relative_path: str,
        vault: str = default_vault,
        doc_id: str | None = None,
        title: str | None = None,
        doc_type: str | None = None,
        system: str | None = None,
        environment: str | None = None,
        status: str | None = None,
        sensitivity: str | None = None,
        tags: list[str] | None = None,
        add_tags: list[str] | None = None,
        remove_tags: list[str] | None = None,
        related_projects: list[str] | None = None,
        add_related_projects: list[str] | None = None,
        remove_related_projects: list[str] | None = None,
        related_assets: list[str] | None = None,
        add_related_assets: list[str] | None = None,
        remove_related_assets: list[str] | None = None,
        last_reviewed: str | None = None,
        touch_last_reviewed: bool = False,
    ) -> dict[str, Any]:
        """Create or update a doc's frontmatter, validated against the vault's schema.

        A file without frontmatter gets a new block (doc_id, title, doc_type and
        system are required; environment, status and sensitivity default to
        other, active, internal). A file with frontmatter is updated in place:
        omitted fields stay as they are, and doc_id can never change.

        Args:
            relative_path: Path from the vault root, e.g. "03 Runbooks/Add Proxy Host.md".
            vault: Which vault.
            doc_id: Stable id; required to create, must match when updating.
            title, doc_type, system, environment, status, sensitivity: Field values.
            tags, related_projects, related_assets: Replace the list.
            add_* / remove_*: Append to or remove from the list (update only).
            last_reviewed: ISO date. Defaults to today on create.
            touch_last_reviewed: Set last_reviewed to today (update).
        """
        ctx = ctx_for(vault)
        return vault_write_service.set_frontmatter(
            ctx.loader,
            relative_path,
            doc_id=doc_id,
            title=title,
            doc_type=doc_type,
            system=system,
            environment=environment,
            status=status,
            sensitivity=sensitivity,
            tags=tags,
            add_tags=add_tags,
            remove_tags=remove_tags,
            related_projects=related_projects,
            add_related_projects=add_related_projects,
            remove_related_projects=remove_related_projects,
            related_assets=related_assets,
            add_related_assets=add_related_assets,
            remove_related_assets=remove_related_assets,
            last_reviewed=last_reviewed,
            touch_last_reviewed=touch_last_reviewed,
            profile=ctx.profile,
        )

    @tool
    def update_link(
        doc_id: str,
        label: str,
        expected_href: str,
        replacement_href: str,
        vault: str = default_vault,
    ) -> dict[str, Any]:
        """Replace one exact Markdown link in a doc, atomically.

        Exactly one link with this label and href must match, both URLs must be
        absolute http(s), and restricted docs are refused.

        Args:
            doc_id: The doc's stable id.
            label: The link's exact visible label.
            expected_href: The exact current URL.
            replacement_href: The new URL.
            vault: Which vault.
        """
        return vault_write_service.update_document_link(
            ctx_for(vault).loader, doc_id, label, expected_href, replacement_href
        )

    # ----- tasks ---------------------------------------------------------------

    @tool
    def task_board(
        vault: str = default_vault,
        status: str | None = None,
        project: str | None = None,
        stale_only: bool = False,
        include_all: bool = False,
        stale_days: int = 14,
    ) -> dict[str, Any]:
        """A vault's task board: open work, counts, recently shipped, and the projects tasks can go in.

        Args:
            vault: Which vault.
            status: Only this status (open, active, parked, done, wontfix).
            project: Only this project (folder name or a related_projects link).
            stale_only: Only open or active tasks untouched past stale_days.
            include_all: Include parked, done and wontfix.
            stale_days: Stale window in days.
        """
        loader = ctx_for(vault).loader
        board = task_service.list_tasks(
            loader,
            status=status,
            project=project,
            stale_only=stale_only,
            include_all=include_all,
            stale_days=stale_days,
        )
        board["projects"] = task_service.list_projects(loader)["projects"]
        return board

    @tool
    def task_write(
        action: TaskAction,
        vault: str = default_vault,
        title: str | None = None,
        project: str | None = None,
        related_projects: list[str] | None = None,
        effort: str = "S",
        priority: str = "med",
        tags: list[str] | None = None,
        problem: str | None = None,
        fix: str | None = None,
        principle: str | None = None,
        source: str | None = None,
        doc_id: str | None = None,
        status: str | None = None,
        note_path: str | None = None,
    ) -> dict[str, Any]:
        """Change a vault's tasks.

        add: file a task (title; optional project, related_projects, effort S|M|L,
            priority high|med|low, tags, and the body sections problem, fix,
            principle, source). Without project it goes to the cross-cutting backlog.
        status: move doc_id to status (open, active, parked, done, wontfix);
            done stamps `closed:`.
        promote: turn the inbox note at note_path into a task titled title,
            keeping its body and removing the note.
        delete: remove doc_id permanently (mistakes only; finished work is
            status done or wontfix).

        Args:
            action: add, status, promote or delete.
            vault: Which vault.
        """
        return _task_write(
            ctx_for(vault),
            action,
            title=title,
            project=project,
            related_projects=related_projects,
            effort=effort,
            priority=priority,
            tags=tags,
            problem=problem,
            fix=fix,
            principle=principle,
            source=source,
            doc_id=doc_id,
            status=status,
            note_path=note_path,
        )
