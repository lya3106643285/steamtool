"""Launcher environment selection and missing-environment diagnostics."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest



ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def launcher(tmp_path):
    project = tmp_path / 'project with spaces'
    project.mkdir()
    shutil.copy2(ROOT / 'start', project / 'start')
    (project / 'main.py').write_text('import sys; print(repr(sys.argv[1:]))\n')
    env = {k: v for k, v in os.environ.items() if k not in {'STEAM_CONDA_PREFIX', 'CONDA_PREFIX', 'CONDA_DEFAULT_ENV'}}
    # Do not discover the developer's real named environments in isolated tests.
    env['CONDA_EXE'] = '/nonexistent/test-conda'
    return project, env


def invoke(project, env, *args):
    return subprocess.run([str(project / 'start'), *args], env=env, cwd='/tmp', capture_output=True, text=True, timeout=5)


def test_project_environment_precedes_unrelated_active_environment(launcher):
    project, env = launcher
    (project / '.conda').symlink_to(sys.prefix, target_is_directory=True)
    env['CONDA_PREFIX'] = '/nonexistent/unrelated-environment'
    query = 'A game with spaces; $(no-shell-evaluation)'
    result = invoke(project, env, 'game', query)
    assert result.returncode == 0 and repr(query) in result.stdout


def test_active_environment_is_used_when_project_environment_absent(launcher):
    project, env = launcher
    env['CONDA_PREFIX'] = sys.prefix
    result = invoke(project, env, '--help')
    assert result.returncode == 0 and '--help' in result.stdout


def test_explicit_override_precedes_project_environment(launcher):
    project, env = launcher
    (project / '.conda').symlink_to(sys.prefix, target_is_directory=True)
    env['STEAM_CONDA_PREFIX'] = '/nonexistent/explicit-environment'
    result = invoke(project, env, '--help')
    assert result.returncode == 1 and 'Conda' in result.stderr and result.stdout == ''


def test_legacy_venv_is_not_selected_and_missing_conda_explained(launcher):
    project, env = launcher
    (project / '.venv').symlink_to(sys.prefix, target_is_directory=True)
    result = invoke(project, env, '--help')
    assert result.returncode == 1 and 'conda env create' in result.stderr
    assert result.stdout == ''


def named_conda(project, env):
    named = project.parent / 'custom envs' / 'steamtool'
    named.parent.mkdir()
    named.symlink_to(sys.prefix, target_is_directory=True)
    command = project.parent / 'test-conda'
    command.write_text('#!/bin/sh\nif [ "$1" = "info" ]; then\n  printf "%s\\n" "$TEST_CONDA_BASE"\nelse\n  printf "%s\\n" "$TEST_CONDA_ENVS"\nfi\n')
    command.chmod(0o755)
    import json
    env.update(CONDA_EXE=str(command), TEST_CONDA_BASE=sys.prefix,
               TEST_CONDA_ENVS=json.dumps({'envs': [sys.prefix, str(named)]}))
    return named


def test_named_environment_precedes_project_and_unrelated_active(launcher):
    project, env = launcher
    named_conda(project, env)
    (project / '.conda').mkdir()  # Invalid legacy environment must not win.
    env['CONDA_PREFIX'] = '/nonexistent/unrelated-environment'
    result = invoke(project, env, '--help')
    assert result.returncode == 0 and '--help' in result.stdout


def test_named_environment_is_used_without_project_or_activation(launcher):
    project, env = launcher
    named_conda(project, env)
    result = invoke(project, env, 'game', 'Portal 2')
    assert result.returncode == 0 and "'Portal 2'" in result.stdout
