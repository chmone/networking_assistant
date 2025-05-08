---
description: A log of key learnings, common pitfalls, and reminders for the AI assistant to improve collaboration and avoid repeating mistakes.
globs: [] # Not a rule for code, but a log for behavior
alwaysApply: false
---

# AI Self-Correction Log & Reminders

This document serves as a running list of important realizations, common issues encountered, and best practices to follow during our collaboration. The goal is to improve efficiency and reduce repeated errors.

## 1. Terminal Commands & File Paths

*   **Working Directory:** The `run_terminal_cmd` tool operates from the project root (e.g., `C:\Users\Cam\Documents\Projects\networking_assistant`). Relative paths used in commands (e.g., `pytest tests/module/test_file.py`) are resolved from this root, which is standard and generally correct.
*   **Path-Like Errors vs. Actual Path Errors:** Be aware that issues *appearing* to be path-related (especially `ImportError`, `ModuleNotFoundError`) can often stem from:
    *   Python's import resolution mechanisms (`sys.path`, `PYTHONPATH` environment variable, how modules import each other with relative vs. absolute paths).
    *   Configuration of tools like `pytest` (e.g., `pythonpath` setting in `pytest.ini`).
    *   Environment inconsistencies.
    *   Typos in file or directory names within import statements or command arguments.
*   **Troubleshooting:** Before assuming the CWD is wrong, verify the exact error message, check `pytest.ini`, and examine import statements in the relevant files.

## 2. Mocking with `unittest.mock` (and `pytest-mock`)

*   **`side_effect` with Lambdas:**
    *   For `mock_obj.method.side_effect`, prefer defining a separate helper function over complex lambdas, especially those with nested conditionals or multiple statements. This avoids subtle `SyntaxError` issues and improves readability.
    *   *Example:*
        ```python
        # Less Preferred (prone to SyntaxError for complex logic)
        # mock_obj.method.side_effect = lambda x, y: val1 if x else (val2 if y else default_val)

        # Preferred
        def my_side_effect(x, y, default=None): # Ensure signature matches original or typical usage
            if x: return val1
            if y: return val2
            return default # Or default_val if that's the intent
        mock_obj.method.side_effect = my_side_effect
        ```
*   **`AttributeError: Mock object has no attribute 'method_name'`:**
    *   When mocking a class instance (e.g., `mock_instance = MagicMock(spec=ClassName)`), if you intend to control a method like `method_name`, ensure it's properly set up on the mock instance.
    *   Simply creating `mock_instance = MagicMock(spec=ClassName)` does not always mean `mock_instance.method_name` is immediately a pre-configured mock ready for `side_effect` or assertions without further setup, especially if the `spec` interaction is tricky.
    *   **Robust approach for fixture/test setup:**
        ```python
        mock_instance = MagicMock(spec=ClassName)
        mock_instance.method_to_mock = MagicMock(return_value=...) # or side_effect=...
        # Now you can safely use mock_instance.method_to_mock.assert_called_with(...)
        # or in the code: result = real_object_using_mock.method_to_mock()
        ```
    *   Always verify the *exact* name and signature of the method being mocked by checking the source code. Typos or incorrect assumptions (e.g., `scrape_leads` vs. `scrape_pms_by_location`) will lead to `AttributeError` during test setup or `AssertionError` (mock not called as expected) during test execution.

## 3. Python Imports & Module Resolution

*   **`ImportError` / `ModuleNotFoundError`:** These are common and require careful debugging:
    *   **Dependencies:** Is the package listed in `requirements.txt`? Has `pip install -r requirements.txt` been run successfully since the last change?
    *   **Relative vs. Absolute Imports:** Check import statements within the failing module and the modules it imports.
        *   `from ..module import X` (relative) might fail if the script is run in a way that Python doesn't recognize its package structure.
        *   Prefer direct imports like `from package.module import X` when the `PYTHONPATH` or `sys.path` is correctly configured (e.g., via `pytest.ini`'s `pythonpath = src`).
    *   **`pytest.ini` for `pytest`:** Ensure `pythonpath = src` (or other relevant source directories) is in `pytest.ini` so `pytest` can find top-level packages in your `src` directory.
    *   **Robust Imports in Modules:** For modules that might be run as standalone scripts *or* imported as part of a larger package, consider robust import blocks (try-except with `sys.path` manipulation as a fallback), but heavily favor configuring the environment correctly (e.g., `pythonpath`) so these fallbacks are rarely needed.
*   **`NameError`:** Often means a necessary import is missing *in the current file where the error occurs*.
    *   Double-check that all names used (variables, functions, classes, custom exceptions) are either defined locally within the file/scope or explicitly imported into that file.
    *   *Example (Custom Exceptions):* If `module_A.py` defines `CustomError`, and `module_B.py` needs to `raise CustomError`, then `module_B.py` must have `from module_A import CustomError` (or similar).

## 4. Tool Behavior Quirks

*   **`edit_file` Tool:**
    *   Occasionally, `edit_file` might not apply changes exactly as intended, or it might introduce extraneous content (e.g., `</rewritten_file>`).
    *   If tests fail unexpectedly after an `edit_file` operation:
        1.  Use `read_file` on the target file to verify its actual content.
        2.  If the diff shown in the `edit_file` result seems incorrect or was not fully applied, consider using the `reapply` tool.
        3.  If problems persist, inform the user and ask them to manually verify or correct the file. This can save significant time debugging ghost issues.
*   **`run_terminal_cmd` Interruptions:**
    *   If a terminal command appears to be cancelled or produces no output when output is expected (especially for `pytest`), ask the user to run the command manually in their own terminal and provide the output. This helps distinguish between tool/environment issues and actual errors in the code or tests.

## 5. General Test Writing

*   **Verify Method Names:** When asserting mock calls (e.g., `mock_obj.method_name.assert_called_once_with(...)`), always double-check the *exact* method name in the source code of the class being mocked.
*   **Focus on One Failure at a Time:** When `pytest` reports multiple failures, address the first one. Subsequent errors might be cascading effects of the initial problem.
*   **`AssertionError` during Parsing Tests:**
    *   When parsing logic (e.g., regex, string splitting) fails an assertion, check both the parsing code and the test's expected value.
    *   The parsing heuristic might be too simple or too greedy for the specific input data in the test case. Refine the parsing logic.
    *   Alternatively, the test assertion might be based on an outdated understanding of the parsing logic. Correct the assertion to match the intended (and now verified) behavior.
    *   *Example:* If parsing `"Role - Company"` sets `role="Role"`, `company="Company"`, an assertion expecting `role=="Role - Company"` is incorrect.
*   **`StopIteration` during Parsing Tests:**
    *   Often occurs when using `next(item for item in results if condition)` and no item matches the condition.
    *   This points to an issue with the data extraction *before* the condition is checked. For example, if extracting `lead_name` incorrectly includes extra characters (`"Bob Simple | LinkedIn"` instead of `"Bob Simple"`), the condition `if lead_name == "Bob Simple"` will fail. Fix the upstream data extraction.
*   **Testing Decorated Functions:**
    *   **Preserving Metadata:** Ensure decorators use `@functools.wraps(func)` to preserve the original function's metadata (like `__name__`, `__doc__`). Lack of this can cause issues with introspection or testing frameworks, potentially leading to `AttributeError: 'function' object has no attribute '__wrapped__'` if trying to access the original function.
    *   **Testing the Decorator vs. Decorated Function:**
        *   To test the *decorator's logic* (e.g., retry counts, delays, exception catching), call the *decorated* function and assert the expected behavior (e.g., number of calls via mocks, specific exceptions raised after retries).
        *   To test the *original function's logic* in isolation (without the decorator's effects), you *can* access the undecorated function using `decorated_function.__wrapped__(...)`. However, this often indicates the decorator is tightly coupled or the tests need rethinking. Prefer testing the integrated behavior unless absolutely necessary.
        *   **If tests fail when calling the decorated function but pass when calling `__wrapped__`:** This strongly suggests an issue in the decorator's interaction with the function or the exceptions it handles (e.g., decorator catching an exception the test expects to be raised further up).
*   **Handling Persistent Test Failures:**
    *   If a subset of tests for a module consistently fails despite numerous fixes, while tests for methods *using* that failing component pass, consider deferring the failing tests.
    *   Document the specific failures and the reasoning for deferral (e.g., core logic seems okay based on integration points, suspected complex mocking interaction).
    *   Focus on achieving coverage for the public API and core functionality first. Revisit the deferred tests later if they become relevant or block further development.
*   **Terminal Tool Reliability:**
    *   Be aware that terminal commands executed via tools (like `run_terminal_cmd`) might hang or be interrupted, especially for longer-running processes like test suites with many tests or delays (e.g., from `time.sleep` in retry logic).
    *   If a command seems to hang repeatedly, ask the user to run it manually and provide the output for reliable results.
*   **Configuration/Dependency Setup:**
    *   Ensure all required external packages (`serpapi`) are listed in `requirements.txt` and installed.
    *   Verify configuration files (`pytest.ini`) have necessary settings (e.g., `pythonpath = src`) for the test runner to find modules correctly.

*(This log will be updated as new patterns or important reminders emerge.)* 