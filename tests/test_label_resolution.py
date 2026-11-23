"""
Unit tests for label_resolution.py (Team 1 feature 1, tested by Team 4).

White-box tests for every method of LabelResolutionAnalysis:
  * get_resolution_date: every branch of the closing-event filter,
  * calculate_resolution_times: open / missing-date / no-close /
    negative-duration / bad-label branches and the printed counts,
  * run(): the "no data" and "no label with 5 issues" early exits and the
    full report + bar chart (no chart window is ever opened).

All issues are built in memory, so the real Poetry data file is not needed.
"""

import contextlib
import io
import unittest
from unittest import mock

import matplotlib
matplotlib.use('Agg')  # never open a chart window while testing
import matplotlib.pyplot as plt

import label_resolution
from label_resolution import LabelResolutionAnalysis
from model import Issue


# ------------------------------------------------------------------ helpers

def make_event(event_type, date='2024-01-02T00:00:00Z'):
    return {'event_type': event_type, 'author': 'someone', 'event_date': date}


def make_issue(number, labels=(), events=(), created='2024-01-01T00:00:00Z',
               state='closed'):
    return Issue({'number': number, 'creator': 'reporter', 'state': state,
                  'labels': list(labels), 'created_date': created,
                  'events': list(events)})


def closed_after(days, labels, number=1):
    """A closed issue created 2024-01-01 and closed `days` days later."""
    return make_issue(number, labels=labels, events=[
        make_event('closed', f'2024-01-{1 + days:02d}T00:00:00Z')])


def build(issues):
    """Creates the analysis with an in-memory issue list instead of the data file."""
    with mock.patch.object(label_resolution, 'DataLoader') as loader:
        loader.return_value.get_issues.return_value = issues
        return LabelResolutionAnalysis()


def quietly(func, *args):
    """Runs func, returning (result, captured stdout)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = func(*args)
    return result, out.getvalue()


# ------------------------------------------------------------------ tests

class TestInit(unittest.TestCase):

    def test_issues_come_from_data_loader(self):
        issues = [make_issue(1)]
        self.assertIs(build(issues).issues, issues)


class TestGetResolutionDate(unittest.TestCase):

    def setUp(self):
        self.analysis = build([])

    def test_no_events_returns_none(self):
        self.assertIsNone(self.analysis.get_resolution_date(make_issue(1)))

    def test_non_closing_events_are_ignored(self):
        issue = make_issue(1, events=[make_event('commented'), make_event('labeled')])
        self.assertIsNone(self.analysis.get_resolution_date(issue))

    def test_event_without_type_is_ignored(self):
        issue = make_issue(1, events=[make_event(None)])
        self.assertIsNone(self.analysis.get_resolution_date(issue))

    def test_closing_event_without_date_is_ignored(self):
        issue = make_issue(1, events=[make_event('closed', date=None)])
        self.assertIsNone(self.analysis.get_resolution_date(issue))

    def test_latest_close_is_used_when_reopened(self):
        issue = make_issue(1, events=[
            make_event('closed', '2024-01-03T00:00:00Z'),
            make_event('reopened', '2024-01-04T00:00:00Z'),
            make_event('closed', '2024-01-09T00:00:00Z'),
        ])
        date = self.analysis.get_resolution_date(issue)
        self.assertEqual(date.isoformat(), '2024-01-09T00:00:00+00:00')

    def test_event_type_match_is_case_insensitive(self):
        issue = make_issue(1, events=[make_event('CLOSED', '2024-01-05T00:00:00Z')])
        self.assertEqual(self.analysis.get_resolution_date(issue).day, 5)


class TestCalculateResolutionTimes(unittest.TestCase):

    def test_groups_days_by_label(self):
        analysis = build([
            closed_after(2, ['bug', 'cli'], 1),
            closed_after(4, ['bug'], 2),
        ])
        result, _ = quietly(analysis.calculate_resolution_times)
        self.assertEqual(dict(result), {'bug': [2.0, 4.0], 'cli': [2.0]})

    def test_fractional_days(self):
        issue = make_issue(1, labels=['bug'], events=[
            make_event('closed', '2024-01-01T12:00:00Z')])
        result, _ = quietly(build([issue]).calculate_resolution_times)
        self.assertEqual(result['bug'], [0.5])

    def test_open_issues_are_skipped(self):
        issue = make_issue(1, labels=['bug'], state='open',
                           events=[make_event('closed')])
        result, out = quietly(build([issue]).calculate_resolution_times)
        self.assertEqual(dict(result), {})
        self.assertIn('Closed issues: 0', out)

    def test_closed_issue_without_created_date_is_skipped(self):
        issue = make_issue(1, labels=['bug'], created=None,
                           events=[make_event('closed')])
        result, out = quietly(build([issue]).calculate_resolution_times)
        self.assertEqual(dict(result), {})
        self.assertIn('Closed issues: 1', out)
        self.assertIn('without a closing event: 0', out)

    def test_closed_issue_without_close_event_is_counted(self):
        issue = make_issue(1, labels=['bug'], events=[make_event('commented')])
        result, out = quietly(build([issue]).calculate_resolution_times)
        self.assertEqual(dict(result), {})
        self.assertIn('without a closing event: 1', out)

    def test_close_before_creation_is_skipped(self):
        issue = make_issue(1, labels=['bug'], created='2024-02-01T00:00:00Z',
                           events=[make_event('closed', '2024-01-01T00:00:00Z')])
        result, _ = quietly(build([issue]).calculate_resolution_times)
        self.assertEqual(dict(result), {})

    def test_blank_and_non_string_labels_are_skipped(self):
        analysis = build([closed_after(3, ['', '   ', None, 42, 'bug'])])
        result, _ = quietly(analysis.calculate_resolution_times)
        self.assertEqual(dict(result), {'bug': [3.0]})

    def test_issue_with_no_labels_contributes_nothing(self):
        result, _ = quietly(build([closed_after(3, [])]).calculate_resolution_times)
        self.assertEqual(dict(result), {})

    def test_summary_counts_are_printed(self):
        issues = [
            closed_after(1, ['bug'], 1),
            make_issue(2, labels=['bug'], state='open'),
            make_issue(3, labels=['bug'], events=[]),
        ]
        _, out = quietly(build(issues).calculate_resolution_times)
        self.assertIn('Total issues: 3', out)
        self.assertIn('Closed issues: 2', out)
        self.assertIn('without a closing event: 1', out)

    def test_naive_created_date_with_utc_close_date(self):
        """
        model.py provides _as_utc() so that naive and timezone-aware dates can
        be subtracted safely. A created_date without a timezone and a closing
        event in UTC should still give a resolution time instead of crashing.
        """
        issue = make_issue(1, labels=['bug'], created='2024-01-01T00:00:00',
                           events=[make_event('closed', '2024-01-03T00:00:00Z')])
        result, _ = quietly(build([issue]).calculate_resolution_times)
        self.assertEqual(result['bug'], [2.0])


class TestRun(unittest.TestCase):

    def tearDown(self):
        plt.close('all')

    def test_no_usable_data_message(self):
        with mock.patch.object(plt, 'show') as show:
            _, out = quietly(build([]).run)
        self.assertIn('No issues with usable resolution dates and labels were found.', out)
        show.assert_not_called()

    def test_labels_below_five_issues_are_excluded(self):
        issues = [closed_after(d, ['bug'], n) for n, d in enumerate([1, 2, 3, 4], 1)]
        with mock.patch.object(plt, 'show') as show:
            _, out = quietly(build(issues).run)
        self.assertIn('No labels have at least 5 resolved issues.', out)
        show.assert_not_called()

    def _full_run(self):
        # 'fast': 5 issues, median 2 days; 'slow': 5 issues, median 10 days;
        # 'rare': only 2 issues, must be filtered out.
        issues, n = [], 0
        for d in [1, 2, 2, 3, 9]:
            n += 1
            issues.append(closed_after(d, ['fast'], n))
        for d in [8, 9, 10, 11, 20]:
            n += 1
            issues.append(closed_after(d, ['slow'], n))
        for d in [1, 1]:
            n += 1
            issues.append(closed_after(d, ['rare'], n))
        with mock.patch.object(plt, 'show') as show:
            _, out = quietly(build(issues).run)
        return out, show

    def test_report_findings(self):
        out, _ = self._full_run()
        self.assertIn('LABEL RESOLUTION ANALYSIS', out)
        self.assertIn("longest median resolution time is 'slow' at 10.00 days, based on 5 issues", out)
        self.assertIn("shortest median resolution time is 'fast' at 2.00 days, based on 5 issues", out)
        self.assertNotIn('rare', out.split('DETAILED RESULTS')[1])

    def test_detailed_results_sorted_by_median(self):
        out, _ = self._full_run()
        details = out.split('DETAILED RESULTS')[1]
        self.assertLess(details.index('fast'), details.index('slow'))

    def test_bar_chart(self):
        _, show = self._full_run()
        show.assert_called_once()
        ax = plt.gcf().axes[0]
        self.assertEqual(ax.get_title(), 'Median Issue Resolution Time by Label')
        self.assertEqual(ax.get_xlabel(), 'Issue Label')
        self.assertEqual(ax.get_ylabel(), 'Median Days to Close')
        self.assertEqual([t.get_text() for t in ax.get_xticklabels()], ['fast', 'slow'])
        self.assertEqual([p.get_height() for p in ax.patches], [2.0, 10.0])

    def test_single_label_is_both_longest_and_shortest(self):
        issues = [closed_after(d, ['bug'], n) for n, d in enumerate([1, 2, 3, 4, 5], 1)]
        with mock.patch.object(plt, 'show'):
            _, out = quietly(build(issues).run)
        self.assertIn("longest median resolution time is 'bug' at 3.00 days", out)
        self.assertIn("shortest median resolution time is 'bug' at 3.00 days", out)


if __name__ == '__main__':
    unittest.main()
