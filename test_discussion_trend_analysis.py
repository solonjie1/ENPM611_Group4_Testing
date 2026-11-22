import contextlib
import io
import runpy
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from discussion_trend_analysis import DiscussionTrendAnalysis #python being tested
from model import Event, Issue

# Test Variable for issues
def make_issue(number=1, title="Issue", created_date=None, events=None):
    issue = Issue()
    issue.number = number
    issue.title = title
    issue.created_date = created_date
    issue.events = events
    return issue

# Test Variable for events
def make_event(event_type, event_date=None):
    event = Event({"event_type": event_type})
    event.event_date = event_date
    return event

# Test Class for Discussion Trend Analysis
class TestDiscussionTrendAnalysisWhiteBox(unittest.TestCase):
    """Exercise the decision branches in discussion trend analysis."""

    #Set up tear down for the test class above
    def setUp(self):
        self.analysis = DiscussionTrendAnalysis()

    def tearDown(self):
        plt.close("all")

    #test for counting comments in issues with various event types such as closed, commented, and None
    def test_count_comments(self):
        cases = (
            (None, 0),
            ([], 0),
            ([None], 0),
            ([make_event("closed")], 0),
            ([make_event("commented")], 1),
            (
                [
                    make_event("commented"),
                    make_event("closed"),
                    make_event("commented"),
                ],
                2,
            ),
        )
        # make sure the count of comments is correct for each case
        for events, expected in cases:
            with self.subTest(events=events):
                self.assertEqual(
                    self.analysis._count_comments(make_issue(events=events)),
                    expected,
                )
    #test for parsing event dates with various date configurations,timezones, and invalid inputs (a character string, byte string, and invalid integer)
    def test_parse_event_date(self):
        naive_datetime = datetime(2024, 1, 2, 3, 4, 5)
        offset_datetime = datetime(
            2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=3))
        )
        #test of the function returns None for a None input
        self.assertIsNone(self.analysis._parse_event_date(None))
        
        #test that the naive datetime is correctly converted to UTC
        self.assertEqual(
            self.analysis._parse_event_date(naive_datetime),
            naive_datetime.replace(tzinfo=timezone.utc),
        )
        #testing the offset timezone is correctly converted to UTC
        self.assertEqual(
            self.analysis._parse_event_date(offset_datetime),
            datetime(2024, 1, 2, 0, 4, 5, tzinfo=timezone.utc),
        )
        #test that a string representation in Zulu datetime is correctly parsed to its equivalent UTC datetime
        self.assertEqual(
            self.analysis._parse_event_date("2024-01-02T03:04:05Z"),
            datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        )
        #test of invalid inputs(a character string, byte string, and invalid integer)
        self.assertIsNone(self.analysis._parse_event_date("not a date"))
        self.assertIsNone(self.analysis._parse_event_date(b"2024-01-02"))
        self.assertIsNone(self.analysis._parse_event_date(123))
    
    #test for grouping monthly activity using creation and comment and invalid dates
    def test_group_monthly_activity_uses_creation_and_comment_dates(self):
        issues = [
            make_issue(
                created_date="2024-01-15T12:00:00Z",
                events=[
                    make_event("commented", "2024-02-03T12:00:00Z"),
                    make_event("closed", "2024-03-03T12:00:00Z"),
                    make_event("commented", "invalid date"),
                ],
            ),
            make_issue(
                created_date=datetime(2024, 1, 20),
                events=[make_event("commented", "2024-01-22T00:00:00Z")],
            ),
            make_issue(
                created_date="invalid date",
                events=[make_event("commented", None)],
            ),
        ]
        #confirm that issues are grouped by their creation month, while comments are grouped by the month their events occurred
        activity = self.analysis._group_monthly_activity(issues)

        january = datetime(2024, 1, 1, tzinfo=timezone.utc)
        february = datetime(2024, 2, 1, tzinfo=timezone.utc)
        self.assertEqual(list(activity), [january, february])
        self.assertEqual(activity[january], {"issues": 2, "comments": 1})
        self.assertEqual(activity[february], {"issues": 0, "comments": 1})
    
    #test for grouping monthly activity with None events, ensuring that the function correctly 
    #handles issues with no events and returns an empty dictionary 
    def test_group_monthly_activity_ignores_none_events(self):
        issue = make_issue(events=[None])

        self.assertEqual(self.analysis._group_monthly_activity([issue]), {})
    
    #test for grouping monthly activity with inactive months, ensuring that the function 
    #includes all months in the trend analysis, even if there are no issues or comments in those months
    def test_group_monthly_activity_includes_inactive_months_in_trend(self):
        issues = [
            make_issue(created_date="2024-01-05T00:00:00Z", events=[])
            for _ in range(10)
        ]
        issues.extend(
            make_issue(created_date="2024-12-05T00:00:00Z", events=[])
            for _ in range(10)
        )
        issues.append(
            make_issue(
                created_date=None,
                events=[make_event("commented", "2024-06-05T00:00:00Z")],
            )
        )

        monthly_activity = self.analysis._group_monthly_activity(issues)
        expected_months = [
            datetime(2024, month, 1, tzinfo=timezone.utc)
            for month in range(1, 13)
        ]

        with self.subTest("includes inactive calendar months"):
            self.assertEqual(list(monthly_activity), expected_months)
        with self.subTest("classifies the full-period trend"):
            self.assertEqual(
                self.analysis._describe_trend(monthly_activity, "issues"),
                "relatively stable",
            )
    
    """ 
    Test the categorization of issues based on their number of comments, including boundary values and empty input.
        Below is the categorization scheme used in the analysis:
            Categorize issues based on their number of comments.
    
            Low (0-2): Represents minimal discussion or interaction.
            Medium (3-10): Represents a moderate level of discussion.
            High (>10): Represents extensive discussion that may indicate
            complex issues or greater contributor involvement.
    
            These fixed thresholds provide simple and consistent
            categories for comparing discussion activity across issues.
    """
    def test_intensity_distribution_boundaries_and_empty_input(self):
        counts = [
            (make_issue(1), 0),
            (make_issue(2), 2),
            (make_issue(3), -1),
            (make_issue(4), 3),
            (make_issue(5), 10),
            (make_issue(6), 11),
        ]

        self.assertEqual(
            self.analysis._get_intensity_distribution([]),
            {"Low": 0, "Medium": 0, "High": 0},
        )
        self.assertEqual(
            self.analysis._get_intensity_distribution(counts),
            {"Low": 3, "Medium": 2, "High": 1},
        )
    #test for getting the top discussed issues with empty input and non-positive limit values
    def test_top_discussed_empty_and_nonpositive_limit(self):
        counts = [(make_issue(1), 5)]

        self.assertEqual(self.analysis._get_top_discussed_issues([]), [])
        self.assertEqual(
            self.analysis._get_top_discussed_issues(counts, limit=0), []
        )
        self.assertEqual(
            self.analysis._get_top_discussed_issues(counts, limit=-1), []
        )

    #test for getting the top discussed issues with a limit that is greater than the number of issues, 
    #ensuring that all issues are returned in sorted order
    def test_top_discussed_short_list_is_fully_returned(self):
        counts = [(make_issue(2), 3), (make_issue(1), 5)]

        self.assertEqual(
            self.analysis._get_top_discussed_issues(counts, limit=2),
            [(counts[1][0], 5), (counts[0][0], 3)],
        )

    # test for getting the top discussed issues with ties at the cutoff limit, ensuring that all tied issues are included and sorted by title
    def test_top_discussed_sorts_and_includes_cutoff_ties(self):
        same_number_later_title = make_issue(1, "Z title")
        same_number_earlier_title = make_issue(1, "A title")
        counts = [
            (make_issue(6), 8),
            (make_issue(5), 7),
            (make_issue(4), 6),
            (same_number_later_title, 5),
            (make_issue(3), 5),
            (same_number_earlier_title, 5),
        ]

        result = self.analysis._get_top_discussed_issues(counts, limit=5)

        self.assertEqual(
            [(issue.number, issue.title, count) for issue, count in result],
            [
                (6, "Issue", 8),
                (5, "Issue", 7),
                (4, "Issue", 6),
                (1, "A title", 5),
                (1, "Z title", 5),
                (3, "Issue", 5),
            ],
        )

    #test for getting discussion hotspots with empty input and zero median, ensuring that the median is 
    #correctly calculated and hotspots are identified
    def test_discussion_hotspots_empty_and_zero_median(self):
        zero_median_counts = [
            (make_issue(1), 0),
            (make_issue(2), 0),
            (make_issue(3), 0),
            (make_issue(4), 2),
            (make_issue(5), 1),
        ]

        self.assertEqual(
            self.analysis._get_discussion_hotspots([]),
            (0.0, []),
        )
        median_comments, hotspots = self.analysis._get_discussion_hotspots(
            zero_median_counts
        )
        self.assertEqual(median_comments, 0.0)
        self.assertEqual(
            [(issue.number, count) for issue, count in hotspots],
            [(4, 2), (5, 1)],
        )

    """
        test for getting discussion hotspots with non-zero median, ensuring that the 
        median is correctly calculated, hotspots are identified based on the threshold, 
        and the results are sorted by issue number

            Comment from the code:
                Identify issues with unusually high discussion activity.
        
                The hotspot threshold is set to twice the median number
                of comments across all issues.
        
                The median is used because it is less sensitive to extreme
                values than the mean. Multiplying it by two provides a
                simple benchmark for identifying issues that receive
                substantially more discussion than a typical issue.
        
                If the median is zero, any issue with at least one comment
                is considered a hotspot.
    """
    def test_discussion_hotspots_nonzero_median_includes_threshold_and_sorts(self):
        counts = [
            (make_issue(3), 6),
            (make_issue(1), 6),
            (make_issue(2), 3),
            (make_issue(4), 1),
            (make_issue(5), 3),
        ]

        median_comments, hotspots = self.analysis._get_discussion_hotspots(counts)

        self.assertEqual(median_comments, 3.0)
        self.assertEqual(
            [(issue.number, count) for issue, count in hotspots],
            [(1, 6), (3, 6)],
        )

    #test for describing trends with insufficient monthly data, ensuring that the function 
    #returns the expected message when there are not enough months to compare
    def test_describe_trend_insufficient_months(self):
        self.assertEqual(
            self.analysis._describe_trend({}, "issues"),
            "stable (not enough monthly data to compare)",
        )
        self.assertEqual(
            self.analysis._describe_trend(
                {datetime(2024, 1, 1): {"issues": 3}}, "issues"
            ),
            "stable (not enough monthly data to compare)",
        )

    #test for describing trends with increasing, decreasing, and stable monthly activity, 
    #ensuring that the function correctly identifies the trend based on the values provided
    def test_describe_trend_increasing_decreasing_and_stable(self):
        cases = (
            ([1, 1, 10, 10], "increasing"),
            ([10, 10, 1, 1], "decreasing"),
            ([10, 10, 11, 11], "relatively stable"),
            ([1, 1, 1, 3], "increasing"),
        )

        for values, expected in cases:
            with self.subTest(values=values):
                monthly_activity = {
                    datetime(2024, month, 1): {"issues": value}
                    for month, value in enumerate(values, start=1)
                }
                self.assertEqual(
                    self.analysis._describe_trend(monthly_activity, "issues"),
                    expected,
                )

    #test for showing the monthly activity chart, ensuring that the chart is created with the correct data and labels
    def test_show_monthly_activity_chart(self):
        monthly_activity = {
            datetime(2024, 1, 1, tzinfo=timezone.utc): {
                "issues": 2,
                "comments": 3,
            },
            datetime(2024, 2, 1, tzinfo=timezone.utc): {
                "issues": 4,
                "comments": 5,
            },
        }

        self.analysis._show_monthly_activity_chart(monthly_activity)

        axes = plt.gcf().axes[0]
        self.assertEqual(len(axes.lines), 2)
        self.assertEqual(list(axes.lines[0].get_ydata()), [2, 4])
        self.assertEqual(list(axes.lines[1].get_ydata()), [3, 5])
        self.assertEqual(axes.get_ylabel(), "Number of Activities")

    #test for showing the monthly activity chart with no data, ensuring that the 
    #function correctly handles the case where there is no data to display and does not raise an error
    def test_show_monthly_activity_chart_with_no_data(self):
        self.analysis._show_monthly_activity_chart({})

    #test for showing the intensity chart, ensuring that the chart is created with the correct data and labels
    def test_show_intensity_chart(self):
        self.analysis._show_intensity_chart(
            {"Low": 0, "Medium": 2, "High": 1}
        )

        axes = plt.gcf().axes[0]
        self.assertEqual([bar.get_height() for bar in axes.patches], [0, 2, 1])
        self.assertEqual(axes.get_ylim(), (0.0, 3.2))
        self.assertEqual(axes.get_ylabel(), "Number of issues")

    #test for printing the report with empty data, ensuring that the function correctly 
    #handles the case where there is no data to report and outputs the expected messages
    def test_print_report_empty_data_branches(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            DiscussionTrendAnalysis._print_report([], {}, {}, [], 0)

        report = output.getvalue()
        self.assertIn("No valid monthly activity data available.", report)
        self.assertIn("No issues to report.", report)
        self.assertIn("Interpretation: no issue data was available", report)
        self.assertIn("Average comments per issue: 0.00", report)

    #test for printing the report with monthly activity, top issues, and interpretation, 
    #ensuring that the function correctly formats and outputs the report based on the provided data
    def test_print_report_monthly_activity_top_issues_and_interpretation(self):
        january = datetime(2024, 1, 1, tzinfo=timezone.utc)
        february = datetime(2024, 2, 1, tzinfo=timezone.utc)
        march = datetime(2024, 3, 1, tzinfo=timezone.utc)
        issue = make_issue(12, title=None)
        monthly_activity = {
            january: {"issues": 3, "comments": 0},
            february: {"issues": 1, "comments": 2},
            march: {"issues": 4, "comments": 2},
        }
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            DiscussionTrendAnalysis._print_report(
                [(issue, 12)],
                monthly_activity,
                {"Low": 0, "Medium": 0, "High": 1},
                [(issue, 12)],
                12,
            )

        report = output.getvalue()
        self.assertIn("Total issues analyzed: 1", report)
        self.assertIn("January 2024: 3 issues, 0 comments", report)
        self.assertIn("Issue creation trend: decreasing.", report)
        self.assertIn("Comment activity trend: increasing.", report)
        self.assertIn("Highest comment activity: February 2024, March 2024", report)
        self.assertIn("Lowest comment activity: January 2024", report)
        self.assertIn("#12: Untitled issue (12 comments)", report)
        self.assertIn("100.0% of issues generated more than 10 comments", report)
    
    #test for printing additional insights with zero median and no hotspots, 
    #ensuring that the function correctly outputs the hotspot threshold and 
    #indicates that no discussion hotspots were found
    def test_print_additional_insights_zero_median_without_hotspots(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.analysis._print_additional_insights(0, [])

        insights = output.getvalue()
        self.assertIn("Hotspot threshold: More than 0 comments", insights)
        self.assertIn("No discussion hotspots found.", insights)

    #test for printing additional insights with a positive median and hotspots, 
    #ensuring that the function correctly outputs the hotspot threshold, number of hotspots, 
    #and details of the issues that meet the hotspot criteria
    def test_print_additional_insights_positive_median_limits_display(self):
        hotspots = [
            (make_issue(number), 20 - number)
            for number in range(1, 12)
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.analysis._print_additional_insights(2.5, hotspots)

        insights = output.getvalue()
        self.assertIn("Hotspot threshold: At least 5.00 comments", insights)
        self.assertIn("Number of discussion hotspots: 11", insights)
        self.assertIn("Issue #10:", insights)
        self.assertNotIn("Issue #11:", insights)

    #test for running the analysis and visualization for issues, ensuring that the 
    #analysis correctly processes the issues, generates the expected charts, and displays them
    #patch is used to mock the data loading and chart display functions, allowing the test to focus 
    #on the analysis logic without relying on external dependencies or actual chart rendering and 
    #does not change the source code being tested, but instead replaces the specified methods with 
    #mock objects that can be controlled and inspected during the test.
    
    def test_run_wires_analysis_and_visualization_for_issues(self):
        issues = [
            make_issue(
                number=1,
                created_date="2024-01-10T00:00:00Z",
                events=[make_event("commented", "2024-02-10T00:00:00Z")],
            ),
            make_issue(
                number=2,
                created_date="2024-02-10T00:00:00Z",
                events=[make_event("closed")],
            ),
        ]

        with (
            patch(
                "discussion_trend_analysis.DataLoader.get_issues",
                return_value=issues,
            ),
            patch.object(self.analysis, "_show_monthly_activity_chart") as month_chart,
            patch.object(self.analysis, "_show_intensity_chart") as intensity_chart,
            patch("discussion_trend_analysis.plt.show") as show,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.analysis.run()

        month_chart.assert_called_once_with(
            {
                datetime(2024, 1, 1, tzinfo=timezone.utc): {
                    "issues": 1,
                    "comments": 0,
                },
                datetime(2024, 2, 1, tzinfo=timezone.utc): {
                    "issues": 1,
                    "comments": 1,
                },
            }
        )
        intensity_chart.assert_called_once_with(
            {"Low": 2, "Medium": 0, "High": 0}
        )
        show.assert_called_once_with(block=True)

    # Tests the empty-issue path with chart rendering and display mocked, ensuring that the analysis
    # correctly handles the case where there are no issues to analyze and does not raise an error
    def test_run_handles_no_issues(self):
        with (
            patch(
                "discussion_trend_analysis.DataLoader.get_issues",
                return_value=None,
            ),
            patch.object(self.analysis, "_show_monthly_activity_chart"),
            patch.object(self.analysis, "_show_intensity_chart"),
            patch("discussion_trend_analysis.plt.show"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.analysis.run()

    #Test for the module entry point (code that autoruns and is not imported) to ensure that 
    #the main script runs without errors and produces expected output
    def test_module_entrypoint(self):
        issues = [
            make_issue(
                number=1,
                created_date="2024-01-10T00:00:00Z",
                events=[],
            )
        ]
        output = io.StringIO()

        with (
            patch("data_loader.DataLoader.get_issues", return_value=issues),
            patch("matplotlib.pyplot.show"),
            contextlib.redirect_stdout(output),
        ):
            runpy.run_path(
                str(Path(__file__).with_name("discussion_trend_analysis.py")),
                run_name="__main__",
            )

        self.assertIn("DISCUSSION TREND ANALYSIS", output.getvalue())

# Run the unit tests if this script is executed directly
if __name__ == "__main__":
    unittest.main()
