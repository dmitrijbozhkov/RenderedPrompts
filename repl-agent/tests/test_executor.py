from persistent_python_agent import PersistentPythonExecutor


def test_state_dictionary_persists_between_executions(tmp_path):
    executor = PersistentPythonExecutor(tmp_path)

    first = executor.execute("state['answer'] = 42")
    second = executor.execute("print(state['answer'])")

    assert first.ok
    assert second.ok
    assert second.stdout == "42\n"


def test_main_globals_and_functions_persist(tmp_path):
    executor = PersistentPythonExecutor(tmp_path)

    first = executor.execute(
        "factor = 3\n"
        "def multiply(value):\n"
        "    return value * factor\n"
    )
    second = executor.execute("print(multiply(7))")

    assert first.ok
    assert second.ok
    assert second.stdout == "21\n"


def test_execution_errors_are_returned_and_state_is_reserialized(tmp_path):
    executor = PersistentPythonExecutor(tmp_path)

    failed = executor.execute("state['before_error'] = True\nraise ValueError('boom')")
    recovered = executor.execute("print(state['before_error'])")

    assert not failed.ok
    assert failed.error == "ValueError: boom"
    assert "Traceback" in (failed.traceback or "")
    assert recovered.ok
    assert recovered.stdout == "True\n"


def test_stderr_is_captured(tmp_path):
    executor = PersistentPythonExecutor(tmp_path)

    result = executor.execute("import sys\nprint('warning', file=sys.stderr)")

    assert result.ok
    assert result.stderr == "warning\n"
