# -*- coding: utf-8 -*-

import re
from functools import partial

import click
import truffleHogRegexes.regexChecks

from tartufo import config, scanner, util


err = partial(click.secho, fg="red", bold=True, err=True)  # pylint: disable=invalid-name


@click.command(name="tartufo",  # noqa: C901
               context_settings=dict(help_option_names=["-h", "--help"]))
@click.option("--json", help="Output in JSON format.", is_flag=True)
@click.option("--rules", multiple=True, type=click.File("r"),
              help="Path(s) to regex rules json list file(s).")
@click.option("--default-regexes/--no-default-regexes", is_flag=True, default=True,
              help="Whether to include the default regex list when configuring"
                   " search patterns. Only applicable if --rules is also specified."
                   " [default: --default-regexes]")
@click.option("--entropy/--no-entropy", is_flag=True, default=True,
              help="Enable entropy checks. [default: True]")
@click.option("--regex/--no-regex", is_flag=True, default=True,
              help="Enable high signal regexes checks. [default: False]")
@click.option("--since-commit", help="Only scan from a given commit hash.")
@click.option("--max-depth", default=1000000,
              help="The max commit depth to go back when searching for secrets."
                   " [default: 1000000]")
@click.option("--branch", help="Specify a branch name to scan only that branch.")
@click.option("-i", "--include-paths", type=click.File("r"),
              help="File with regular expressions (one per line), at least one of "
                   "which must match a Git object path in order for it to be scanned; "
                   "lines starting with '#' are treated as comments and are ignored. "
                   "If empty or not provided (default), all Git object paths are "
                   "included unless otherwise excluded via the --exclude-paths option.")
@click.option("-x", "--exclude-paths", type=click.File("r"),
              help="File with regular expressions (one per line), none of which may "
                   "match a Git object path in order for it to be scanned; lines "
                   "starting with '#' are treated as comments and are ignored. If "
                   "empty or not provided (default), no Git object paths are excluded "
                   "unless effectively excluded via the --include-paths option.")
@click.option("--repo-path", type=click.Path(),
              help="Path to local repo clone. If provided, git_url will not be used.")
@click.option("--cleanup", is_flag=True, default=False,
              help="Clean up all temporary result files. [default: False]")
@click.option("--pre-commit", is_flag=True, default=False,
              help="Scan staged files in local repo clone.")
@click.argument("git_url", required=False)
@click.pass_context
def main(ctx, **kwargs):
    """Find secrets hidden in the depths of git.

    Tartufo will, by default, scan the entire history of a git repository
    for any text which looks like a secret, password, credential, etc. It can
    also be made to work in pre-commit mode, for scanning blobs of text as a
    pre-commit hook.
    """
    click.echo(dir(ctx))
    click.echo(kwargs)
    if not any((kwargs["entropy"], kwargs["regex"])):
        err("No analysis requested.")
        ctx.exit(1)
    if not any((kwargs["pre_commit"], kwargs["repo_path"], kwargs["git_url"])):
        err("You must specify one of --pre-commit, --repo-path, or git_url.")
        ctx.exit(1)
    try:
        rules_regexes = config.configure_regexes_from_args(
            kwargs,
            truffleHogRegexes.regexChecks.regexes
        )
    except ValueError as exc:
        err(str(exc))
        ctx.exit(1)
    if kwargs["regex"] and not rules_regexes:
        err("Regex checks requested, but no regexes found.")
        ctx.exit(1)

    # read & compile path inclusion/exclusion patterns
    path_inclusions = []
    path_exclusions = []
    if kwargs["include_paths"]:
        for pattern in set(l[:-1].lstrip() for l in kwargs["include_paths"]):
            if pattern and not pattern.startswith("#"):
                path_inclusions.append(re.compile(pattern))
    if kwargs["exclude_paths"]:
        for pattern in set(l[:-1].lstrip() for l in kwargs["exclude_paths"]):
            if pattern and not pattern.startswith("#"):
                path_exclusions.append(re.compile(pattern))

    if kwargs["pre_commit"]:
        output = scanner.find_staged(
            kwargs["repo_path"],
            kwargs["json"],
            kwargs["regex"],
            kwargs["entropy"],
            custom_regexes=rules_regexes,
            suppress_output=False,
            path_inclusions=path_inclusions,
            path_exclusions=path_exclusions,
        )
    else:
        output = scanner.find_strings(
            kwargs["git_url"],
            kwargs["since_commit"],
            kwargs["max_depth"],
            kwargs["json"],
            kwargs["regex"],
            kwargs["entropy"],
            custom_regexes=rules_regexes,
            suppress_output=False,
            branch=kwargs["branch"],
            repo_path=kwargs["repo_path"],
            path_inclusions=path_inclusions,
            path_exclusions=path_exclusions,
        )

    if kwargs["cleanup"]:
        util.clean_outputs(output)
    else:
        issues_path = output.get("issues_path", None)
        if issues_path:
            print("Results have been saved in {}".format(issues_path))

    if output.get("found_issues", False):
        ctx.exit(1)
    ctx.exit(0)
