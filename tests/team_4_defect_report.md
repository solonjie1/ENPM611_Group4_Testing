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


