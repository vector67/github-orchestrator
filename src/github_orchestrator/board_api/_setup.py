import json
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi import Path as PathParameter
from fastapi.responses import JSONResponse

from github_orchestrator.board_api import _etag as etag
from github_orchestrator.board_api._app import PREFIX
from github_orchestrator.board_api._contract import (
    ErrorCode,
    Errors,
    FieldError,
    FieldErrors,
    Login,
    MovedAside,
    Setup,
    SetupAccount,
    SetupClone,
    SetupCloneProgress,
    SetupOperation,
    SetupOptions,
    SetupRepo,
    SetupRepoChoice,
    SetupRepoChoices,
    SetupRequest,
    SetupRequirement,
)
from github_orchestrator.board_api._errors import (
    NOT_FOUND,
    PRECONDITION_FAILED,
    Refusal,
)
from github_orchestrator.board_api.interface import (
    RepoChoice,
    SetupDesk,
    SetupProgress,
    SetupRead,
    SetupWrite,
)
from github_orchestrator.board_api.interface import SetupOptions as Options
from github_orchestrator.board_api.interface import SetupRepo as Picked
from github_orchestrator.domain import Repo


def desk_of(request: Request) -> SetupDesk:
    desk: SetupDesk = request.app.state.desk.setup
    return desk


Desk = Annotated[SetupDesk, Depends(desk_of)]
Owner = Annotated[str, PathParameter(pattern=r"^[A-Za-z0-9_.-]+$")]
Name = Annotated[str, PathParameter(pattern=r"^[A-Za-z0-9_.-]+$")]
LoginParameter = Annotated[str, PathParameter(pattern=r"^[A-Za-z0-9-]+$", max_length=39)]
IfMatch = Annotated[str, Header(
    alias="If-Match",
    description="The `etag` field of the last `GET /api/setup`. Required, so a write never "
                "lands on a config that changed since the page read it.")]

reads = APIRouter(prefix=PREFIX, tags=["setup"])
writes = APIRouter(prefix=PREFIX, tags=["setup"])

NO_TOKEN = {"description": "`no-gh-token`: gh holds no token for the login. The detail "
                           "says to run `gh auth login`.",
            "model": Errors}

UNSEEN = {"description": "`repo-not-visible`: the login cannot see the repo, or there is "
                         "no such repo.",
          "model": Errors}

REFUSED = {"description": "`setup-refused`, one error per field: a repo that is not "
                          "owner/name or that the account cannot see, a clone path holding "
                          "something that is not a clone of its repo, an account gh holds "
                          "no token for, or a config that would not read back. Nothing was "
                          "written or cloned.",
           "model": FieldErrors}

NOT_BROKEN = {"description": "`not-broken`: the config parses, so the page does not move it.",
              "model": Errors}

STARTED = {"description": "Taken. Poll the operation at `Location`.",
           "headers": {"Location": {"schema": {"type": "string", "format": "uri-reference"}}}}


def _revision(read: SetupRead) -> str:
    return etag.etag_of(json.dumps({
        "state": read.state, "config_path": read.config_path, "problem": read.problem,
        "gh_account": read.account, "repos": [asdict(one) for one in read.repos],
        "options": asdict(read.options), "hub_port": read.hub_port}, sort_keys=True).encode())


def _setup_of(read: SetupRead) -> Setup:
    return Setup(
        state=read.state, etag=_revision(read), config_path=read.config_path,
        problem=read.problem, active_account=read.active_account, gh_account=read.account,
        repos=[SetupRepo(**asdict(one)) for one in read.repos],
        options=SetupOptions(**asdict(read.options)), hub_port=read.hub_port,
        agent_name=read.agent_name,
        requirements=[SetupRequirement(program=one.program, fix=one.fix)
                      for one in read.requirements])


def _choice_of(choice: RepoChoice) -> SetupRepoChoice:
    return SetupRepoChoice(repo=str(choice.repo), can_push=choice.can_push,
                           has_my_prs=choice.has_my_prs, default_branch=choice.default_branch)


def _operation_of(progress: SetupProgress) -> SetupOperation:
    return SetupOperation(
        id=progress.id, state=progress.state, error=progress.error,
        clones=[SetupCloneProgress(repo=str(one.repo), path=one.path, state=one.state,
                                   error=one.error) for one in progress.clones],
        archived=list(progress.archived), kept_worktrees=list(progress.kept_worktrees))


def _started(progress: SetupProgress) -> Response:
    return JSONResponse(status_code=202, content=_operation_of(progress).model_dump(mode="json"),
                        headers={"Location": f"{PREFIX}/setup/operations/{progress.id}"})


@reads.get("/setup", response_model=Setup, operation_id="readSetup",
           summary="The hub's state and the config as it stands, for the setup screen.",
           responses=etag.TAGGED)
def read_setup(request: Request, desk: Desk) -> Response:
    """Reads only: opening the setup screen on a hub that watches writes nothing."""
    return etag.answered(request, _setup_of(desk.read()))


@reads.get("/setup/accounts/{login}", response_model=SetupAccount,
           operation_id="readSetupAccount", responses={404: NO_TOKEN},
           summary="Whether gh holds a token for the login, and its scopes.")
def read_account(login: LoginParameter, desk: Desk) -> SetupAccount:
    scopes = desk.scopes(login)
    if isinstance(scopes, str):
        raise Refusal(404, ErrorCode.NO_GH_TOKEN, scopes)
    return SetupAccount(login=login, scopes=list(scopes))


@reads.get("/setup/accounts/{login}/repos", response_model=SetupRepoChoices,
           operation_id="listSetupRepos", responses={404: NO_TOKEN},
           summary="The repos the login can reach, newest push first.")
def list_repos(login: LoginParameter, desk: Desk) -> SetupRepoChoices:
    """Every repo the login owns, collaborates on or reaches through an
    organisation, with whether it may push. Kept for a minute."""
    found = desk.repos(login)
    if isinstance(found, str):
        raise Refusal(404, ErrorCode.NO_GH_TOKEN, found)
    return SetupRepoChoices(login=login, repos=[_choice_of(one) for one in found])


@reads.get("/setup/repos/{owner}/{name}", response_model=SetupRepoChoice,
           operation_id="readSetupRepo", responses={404: UNSEEN},
           summary="One repo typed by name, as the login sees it.")
def read_repo(owner: Owner, name: Name, login: Login, desk: Desk) -> SetupRepoChoice:
    found = desk.repo(login, Repo(owner, name))
    if isinstance(found, str):
        raise Refusal(404, ErrorCode.REPO_NOT_VISIBLE, found)
    return _choice_of(found)


@reads.get("/setup/clones/{owner}/{name}", response_model=SetupClone,
           operation_id="readSetupClone",
           summary="Where the repo's clone is or would go, and whether one is there.")
def read_clone(owner: Owner, name: Name, desk: Desk) -> SetupClone:
    spot = desk.clone(Repo(owner, name))
    return SetupClone(repo=str(spot.repo), path=spot.path, exists=spot.exists,
                      is_clone=spot.is_clone)


@writes.put("/setup", status_code=202, response_model=SetupOperation,
            operation_id="writeSetup",
            responses={202: STARTED, 412: PRECONDITION_FAILED, 422: REFUSED},
            summary="Write the whole config, clone what is missing, and restart the watcher.")
def write_setup(asked: SetupRequest, if_match: IfMatch, desk: Desk) -> Response:
    """Checks every field first and refuses with `422` before anything is
    written. Then clones the repos whose clone is missing, archives the
    state of repos no longer watched and closes their pull requests'
    managers and boards, writes the config, and stops the watcher so its
    service starts it again in the state the new config chooses."""
    if if_match != _revision(desk.read()):
        raise Refusal(412, ErrorCode.PRECONDITION_FAILED,
                      f"the config has changed since {if_match} was read")
    taken = desk.write(SetupWrite(
        account=asked.gh_account,
        repos=tuple(Picked(one.repo, one.local_path, one.new_worktree_command)
                    for one in asked.repos),
        options=Options(asked.options.agent_model, asked.options.agents_enabled,
                        asked.options.max_thread_runs),
        hub_port=asked.hub_port))
    if isinstance(taken, list):
        return JSONResponse(status_code=422, content=FieldErrors(errors=[
            FieldError(status=422, code=ErrorCode.SETUP_REFUSED, detail=one.detail,
                       field=one.field) for one in taken]).model_dump(mode="json"))
    return _started(taken)


@reads.get("/setup/operations/{operation}", response_model=SetupOperation,
           operation_id="readSetupOperation", responses={404: NOT_FOUND},
           summary="How a setup write is going.")
def read_operation(operation: str, desk: Desk) -> SetupOperation:
    progress = desk.progress(operation)
    if progress is None:
        raise Refusal(404, ErrorCode.NOT_FOUND, f"no setup write {operation}")
    return _operation_of(progress)


@writes.post("/setup:move-aside", status_code=202, response_model=MovedAside,
             operation_id="moveConfigAside", responses={409: NOT_BROKEN},
             summary="Rename a broken config and restart the watcher into setup.")
def move_aside(desk: Desk) -> MovedAside:
    moved = desk.move_aside()
    if moved is None:
        raise Refusal(409, ErrorCode.NOT_BROKEN, "the config parses, so it stays where it is")
    return MovedAside(moved_to=moved)
