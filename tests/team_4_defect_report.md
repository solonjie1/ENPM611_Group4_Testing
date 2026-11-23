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


