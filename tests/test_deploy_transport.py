"""Retry only rejected Horde operations; ambiguous append uploads must stop."""
import importlib.util
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import deploy_horde


def completed(code=0, stderr=''):
    return subprocess.CompletedProcess([], code, '', stderr)


def test_definite_busy_rejection_checks_worker_before_bounded_retry():
    busy = completed(1, 'hgx exec failed (HTTP 409): operation_in_progress')
    with patch.object(deploy_horde.subprocess, 'run', side_effect=[busy, completed(), completed()]) as run, patch.object(deploy_horde.time, 'sleep') as sleep:
        deploy_horde.remote('worker', 'append-public-chunk')
    assert run.call_args_list[1].args[0] == ['hgx', '--json', 'status', 'worker']
    assert run.call_args_list[0].args == run.call_args_list[2].args
    sleep.assert_called_once_with(2)


def test_ambiguous_transport_failure_is_not_retried_or_payload_echoed():
    with patch.object(deploy_horde.subprocess, 'run', return_value=completed(1, 'hgx exec failed (HTTP 502)')) as run, patch.object(deploy_horde.time, 'sleep') as sleep:
        with pytest.raises(RuntimeError, match='HTTP 502') as error:
            deploy_horde.remote('worker', 'large-append-payload')
    assert run.call_count == 1
    sleep.assert_not_called()
    assert 'large-append-payload' not in str(error.value)


def test_busy_retry_budget_is_finite():
    busy = completed(1, 'HTTP 409 operation_in_progress')
    with patch.object(deploy_horde.subprocess, 'run', side_effect=[busy, completed(), busy, busy, busy]) as run, patch.object(deploy_horde.time, 'sleep') as sleep:
        with pytest.raises(RuntimeError, match='HTTP 409'):
            deploy_horde.remote('worker', 'append-public-chunk')
    assert run.call_count == 5 and sleep.call_count == 3
