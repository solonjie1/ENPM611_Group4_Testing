Defect title: None events crash monthly activity grouping
Affected module or feature: Discussion Trend Analysis (`discussion_trend_analysis.py`)
Associated test case: `test_group_monthly_activity_ignores_none_events`
Preconditions or test data: Issue with `events=[None]`
Steps to reproduce:
1. Create a `DiscussionTrendAnalysis` instance.
2. Call `_group_monthly_activity([issue])`.
Expected result: A `None` event is ignored and an empty activity dictionary is returned.
Actual result: The method raises `AttributeError: 'NoneType' object has no attribute 'event_type'`.
Relevant failure output: `discussion_trend_analysis.py:81` executes `event.event_type` without first checking whether `event` is `None`.

Defect title: Unsupported integer date value raises an exception
Affected module or feature: Discussion Trend Analysis (`discussion_trend_analysis.py`)
Associated test case: `test_parse_event_date`
Preconditions or test data: Integer value `123`
Steps to reproduce:
1. Create a `DiscussionTrendAnalysis` instance.
2. Call `_parse_event_date(123)`.
Expected result: Unsupported data types return `None`.
Actual result: The method raises `AttributeError: 'int' object has no attribute 'replace'`.
Relevant failure output: `_parse_event_date()` calls `replace()` on non-string values before converting an invalid type into `None`.

Defect title: Monthly activity omits inactive calendar months
Affected module or feature: Discussion Trend Analysis (`discussion_trend_analysis.py`)
Associated test case: `test_group_monthly_activity_includes_inactive_months_in_trend`
Preconditions or test data: Twenty issues in January and December 2024, plus one commented issue with no creation date in June 2024
Steps to reproduce:
1. Create a `DiscussionTrendAnalysis` instance.
2. Call `_group_monthly_activity(issues)`.
3. Examine every month from January through December.
Expected result: The result contains every month from January through December 2024, including months with zero issues/comments.
Actual result: The result contains only January, June, and December 2024.
Relevant failure output: `AssertionError: ... [2024-01, 2024-06, 2024-12] != [2024-01, 2024-02, ..., 2024-12]`

Defect title: Trend result is incorrect when inactive months are excluded
Affected module or feature: Discussion Trend Analysis (`discussion_trend_analysis.py`)
Associated test case: `test_group_monthly_activity_includes_inactive_months_in_trend`
Preconditions or test data: January/December issue counts plus an isolated June comment, as described by the test
Steps to reproduce:
1. Call `_group_monthly_activity(issues)`.
2. Pass the returned dictionary to `_describe_trend(..., "issues")`.
Expected result: The full-period issue trend is `relatively stable`.
Actual result: The method returns `decreasing`.
Relevant failure output: `AssertionError: 'decreasing' != 'relatively stable'`; inactive months are omitted before trend averages are calculated.

Defect title: Monthly chart crashes with an empty dataset
Affected module or feature: Discussion Trend Analysis (`discussion_trend_analysis.py`)
Associated test case: `test_show_monthly_activity_chart_with_no_data`
Preconditions or test data: Empty monthly activity dictionary `{}`
Steps to reproduce:
1. Create a `DiscussionTrendAnalysis` instance.
2. Call `_show_monthly_activity_chart({})`.
Expected result: The chart method handles an empty dataset without raising an exception.
Actual result: The method raises `IndexError: list index out of range`.
Relevant failure output: `discussion_trend_analysis.py:270` indexes `months[0]` and `months[-1]` while constructing the chart title.

Defect title: Resolution time calculation crashes when one date has a timezone and the other does not
Affected module or feature: Label Resolution Analysis, Feature 1 (`label_resolution.py`)
Associated test case: `test_naive_created_date_with_utc_close_date` (`tests/test_label_resolution.py`, class `TestCalculateResolutionTimes`)
Preconditions or test data: One closed issue labeled `bug` with `created_date` `2024-01-01T00:00:00` (no timezone) and a `closed` event dated `2024-01-03T00:00:00Z` (UTC). `DataLoader` is mocked to return only this issue.
Steps to reproduce:
1. Build the issue above with `model.Issue`.
2. Create a `LabelResolutionAnalysis` instance whose `DataLoader().get_issues()` returns that issue.
3. Call `calculate_resolution_times()`.
4. Or run: `python -m unittest tests.test_label_resolution.TestCalculateResolutionTimes.test_naive_created_date_with_utc_close_date`
Expected result: The method returns `{'bug': [2.0]}` (a 2-day resolution time), because `model.py` provides `_as_utc()` and `Issue.days_to_close()` to normalize both dates to UTC before subtracting.
Actual result: The method raises `TypeError: can't subtract offset-naive and offset-aware datetimes`, which also stops `run()` (and `python run.py --feature 1`) from producing any report or chart.
Relevant failure output:
```
ERROR: test_naive_created_date_with_utc_close_date (tests.test_label_resolution.TestCalculateResolutionTimes)
Traceback (most recent call last):
  File "tests/test_label_resolution.py", line 163, in test_naive_created_date_with_utc_close_date
    result, _ = quietly(build([issue]).calculate_resolution_times)
  File "tests/test_label_resolution.py", line 45, in quietly
    result = func(*args)
  File "label_resolution.py", line 63, in calculate_resolution_times
    close_date - issue.created_date
TypeError: can't subtract offset-naive and offset-aware datetimes
```
`label_resolution.py:62-64` subtracts `issue.created_date` from the closing date directly instead of using `_as_utc()` or `Issue.days_to_close()` from `model.py`.

Defect title: A falsy default value passed to `get_parameter` is ignored
Affected module or feature: Configuration (`config.py`)
Associated test case: `test_missing_parameter_returns_falsy_default` (`tests/test_config.py`, class `TestGetParameter`)
Preconditions or test data: A parameter name that is neither an environment variable nor in `config.json` (`DOES_NOT_EXIST`), and the defaults `0`, `False`, and `''`.
Steps to reproduce:
1. Call `config.get_parameter('DOES_NOT_EXIST', default=0)`.
2. Repeat with `default=False` and `default=''`.
3. Or run: `python -m unittest tests.test_config.TestGetParameter.test_missing_parameter_returns_falsy_default`
Expected result: The supplied default is returned (`0`, `False`, `''`).
Actual result: `None` is returned for each of these defaults.
Relevant failure output:
```
FAIL: test_missing_parameter_returns_falsy_default (tests.test_config.TestGetParameter)
Traceback (most recent call last):
  File "tests/test_config.py", line 122, in test_missing_parameter_returns_falsy_default
    self.assertEqual(config.get_parameter('DOES_NOT_EXIST', default=0), 0)
AssertionError: None != 0
```
`config.py:64` checks `if default:` instead of `if default is not None:`, so any falsy default falls through to `return None`.

Defect title: Loading an issue with no `state` field crashes with `KeyError`
Affected module or feature: Data model (`model.py`, `Issue.from_json`)
Associated test case: `test_issue_without_state_can_still_be_loaded` (`tests/test_model.py`, class `TestIssue`)
Preconditions or test data: A valid issue JSON record (number `7`, state `closed`, dates, labels, etc.) with the `state` key removed.
Steps to reproduce:
1. Build the issue record and delete its `state` key.
2. Call `Issue(record)`.
3. Or run: `python -m unittest tests.test_model.TestIssue.test_issue_without_state_can_still_be_loaded`
Expected result: The issue loads with `state` set to `None`, the same way a missing number or date is tolerated, and the other fields (e.g. `number == 7`) are still read.
Actual result: `Issue(record)` raises `KeyError(None)`. Because `DataLoader` builds every issue this way, one incomplete record makes the whole data file unloadable.
Relevant failure output:
```
FAIL: test_issue_without_state_can_still_be_loaded (tests.test_model.TestIssue)
Traceback (most recent call last):
  File "tests/test_model.py", line 160, in test_issue_without_state_can_still_be_loaded
    self.assertIsNone(crash, 'Issue without a state raised a KeyError instead of loading')
AssertionError: KeyError(None) is not None : Issue without a state raised a KeyError instead of loading
```
`model.py:86` runs `State[jobj.get('state')]` without checking for a missing value, so `State[None]` raises `KeyError`.

Defect title: Feature 2 crashes with an uncaught `FileNotFoundError` when the data file path is wrong
Affected module or feature: Contributor Activity Analysis, Feature 2 (`contributor_activity_analysis.py`)
Associated test case: `test_missing_data_file_gives_a_message_instead_of_a_crash` (`tests/test_contributor_activity_analysis.py`, class `TestRun`)
Preconditions or test data: `ENPM611_PROJECT_DATA_PATH` set to a file that does not exist (`no/such/file.json`) and no issues cached in `data_loader`.
Steps to reproduce:
1. Set `ENPM611_PROJECT_DATA_PATH=no/such/file.json`.
2. Create a `ContributorActivityAnalysis` instance and call `run()` (equivalent to `python run.py --feature 2`).
3. Or run: `python -m unittest tests.test_contributor_activity_analysis.TestRun.test_missing_data_file_gives_a_message_instead_of_a_crash`
Expected result: As the README states ("If the path is missing or wrong, the application prints a clear error message instead of crashing"), `run()` prints the error message and returns without raising.
Actual result: `run()` raises an uncaught `FileNotFoundError`, ending the program with a stack trace.
Relevant failure output:
```
FAIL: test_missing_data_file_gives_a_message_instead_of_a_crash (tests.test_contributor_activity_analysis.TestRun)
Traceback (most recent call last):
  File "tests/test_contributor_activity_analysis.py", line 650, in test_missing_data_file_gives_a_message_instead_of_a_crash
    self.assertIsNone(crash, 'run() crashed with an uncaught FileNotFoundError')
AssertionError: FileNotFoundError("Data file not found: 'no/such/file.json'. Set ENPM611_PROJECT_DATA_PATH (environment variable or config.json) to the path of the issues JSON file.") is not None : run() crashed with an uncaught FileNotFoundError
```
`DataLoader._load()` builds a clear message, but raises it as an exception that `run()` never catches, so the user sees a stack trace instead of the message the README promises.

Defect title: `--user null` is silently ignored and the project-wide view is shown
Affected module or feature: Contributor Activity Analysis, Feature 2 (`contributor_activity_analysis.py`, via `config.py`)
Associated test case: `test_user_called_null_is_treated_as_a_user_name` (`tests/test_contributor_activity_analysis.py`, class `TestUserParameter`)
Preconditions or test data: The `user` parameter set to the text `null` (as `python run.py --feature 2 --user null` does).
Steps to reproduce:
1. Call `config.set_parameter('user', 'null')`.
2. Create a `ContributorActivityAnalysis` instance and read its `USER` attribute.
3. Or run: `python -m unittest tests.test_contributor_activity_analysis.TestUserParameter.test_user_called_null_is_treated_as_a_user_name`
Expected result: `USER == 'null'`, so the name is looked up like any other user (and reported as not found if it has no activity).
Actual result: `USER` is `None`, so the analysis silently shows the project-wide view instead of the requested user.
Relevant failure output:
```
FAIL: test_user_called_null_is_treated_as_a_user_name (tests.test_contributor_activity_analysis.TestUserParameter)
Traceback (most recent call last):
  File "tests/test_contributor_activity_analysis.py", line 171, in test_user_called_null_is_treated_as_a_user_name
    self.assertEqual(self.analysis('null').USER, 'null')
AssertionError: None != 'null'
```
`config.get_parameter` passes the value through `convert_to_typed_value`, which runs `json.loads('null')` and turns the text into `None`; `contributor_activity_analysis.py:49-50` then treats it as "no user given".