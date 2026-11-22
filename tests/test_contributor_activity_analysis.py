"""
Unit tests for contributor_activity_analysis.py (Team 1 feature 2, tested by Team 4).

White-box tests for every method of ContributorActivityAnalysis:
  * _aggregate and _first_responses (the data processing),
  * the console reports, including every branch of the findings,
  * the three charts (matplotlib windows are never opened),
  * run(), for the project-wide view and the --user view.

All issues are built in memory, so the real Poetry data file is not needed.
"""

import contextlib
import io
import os
import runpy
import unittest
from unittest import mock

import matplotlib
matplotlib.use('Agg')  # never open a chart window while testing
import matplotlib.pyplot as plt
import pandas as pd

import config
import contributor_activity_analysis as caa
import data_loader
from contributor_activity_analysis import ContributorActivityAnalysis
from model import Issue


# ------------------------------------------------------------------ helpers

def make_event(event_type, author, date='2024-01-02T00:00:00Z'):
    return {'event_type': event_type, 'author': author, 'event_date': date}


def make_issue(number, creator, events=(), created='2024-01-01T00:00:00Z', state='open'):
    return Issue({'number': number, 'creator': creator, 'state': state,
                  'created_date': created, 'events': list(events)})


def make_activity(rows):
    """
    Builds a table with the same columns as _aggregate() from
    {contributor: (comments, label_actions, closes, issues_touched)}.
    """
    df = pd.DataFrame.from_dict(
        rows, orient='index', columns=['comments', 'label_actions', 'closes', 'issues_touched'])
    df.index.name = 'contributor'
    df['triage_actions'] = df['label_actions'] + df['closes']
    df['total'] = df['comments'] + df['triage_actions']
    return df.sort_values('total', ascending=False)


def make_first(rows):
    """Builds a first-response table from (year, responder, how many issues)."""
    records, number = [], 0
    for year, responder, count in rows:
        for _ in range(count):
            number += 1
            records.append({'issue': number, 'year': year, 'responder': responder})
    return pd.DataFrame(records, columns=['issue', 'year', 'responder'])


def sample_issues():
    """
    Three issues that exercise every classification rule:
      alice: 2 comments, 2 label actions, 1 close  (on issues 1 and 2)
      bob:   2 comments                            (on issues 1 and 2)
    Everything else (reporter's own label/close, bot, unknown author,
    other event types) must be ignored.
    """
    return [
        make_issue(1, 'reporter1', created='2024-01-01T00:00:00Z', events=[
            make_event('labeled', 'reporter1', '2024-01-01T00:00:01Z'),   # own label: ignored
            make_event('commented', 'bob', '2024-01-03T00:00:00Z'),
            make_event('commented', 'alice', '2024-01-02T00:00:00Z'),     # earliest reply
            make_event('labeled', 'alice', '2024-01-02T00:00:00Z'),
            make_event('closed', 'alice', '2024-01-04T00:00:00Z'),
        ]),
        make_issue(2, 'bob', created='2024-02-01T00:00:00Z', events=[
            make_event('commented', 'bob', '2024-02-01T01:00:00Z'),       # own comment: counted, not a reply
            make_event('commented', 'github-actions[bot]', '2024-02-01T02:00:00Z'),
            make_event('commented', 'alice', '2024-02-02T00:00:00Z'),
            make_event('unlabeled', 'alice', '2024-02-02T00:00:00Z'),
            make_event('closed', 'bob', '2024-02-03T00:00:00Z'),          # own close: ignored
        ]),
        make_issue(3, 'carol', created='2023-05-01T00:00:00Z', events=[
            make_event('commented', None, '2023-05-02T00:00:00Z'),        # unknown author
            make_event('subscribed', 'dave', '2023-05-02T00:00:00Z'),     # not a counted event type
        ]),
    ]


def busy_year_issues(count=10, year=2024):
    """`count` issues opened in one year, each answered first by alice, then by bob."""
    return [
        make_issue(n, f'reporter{n}', created=f'{year}-03-01T00:00:00Z', events=[
            make_event('commented', 'alice', f'{year}-03-02T00:00:00Z'),
            make_event('commented', 'bob', f'{year}-03-03T00:00:00Z'),
            make_event('labeled', 'alice', f'{year}-03-02T00:00:00Z'),
        ])
        for n in range(1, count + 1)
    ]


class AnalysisTestCase(unittest.TestCase):
    """Common set-up: clean parameters, no chart windows, captured output."""

    def setUp(self):
        env_patch = mock.patch.dict(os.environ)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        os.environ.pop('user', None)

        show_patch = mock.patch.object(plt, 'show')
        self.show = show_patch.start()
        self.addCleanup(show_patch.stop)
        self.addCleanup(plt.close, 'all')

    def analysis(self, user=None) -> ContributorActivityAnalysis:
        if user is not None:
            config.set_parameter('user', user)
        return ContributorActivityAnalysis()

    @staticmethod
    def capture(func, *args):
        """Calls func and returns (printed text, return value)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = func(*args)
        return out.getvalue(), result

    def run_with(self, issues, user=None):
        """Runs the whole analysis on the given issues; returns the printed text."""
        analysis = self.analysis(user)
        with mock.patch.object(caa.DataLoader, 'get_issues', return_value=issues):
            printed, _ = self.capture(analysis.run)
        return printed


# ------------------------------------------------------------- constructor

class TestUserParameter(AnalysisTestCase):

    def test_no_user_parameter(self):
        self.assertIsNone(self.analysis().USER)

    def test_user_is_read_from_the_configuration(self):
        self.assertEqual(self.analysis('abn').USER, 'abn')

    def test_surrounding_spaces_are_removed(self):
        self.assertEqual(self.analysis('  abn ').USER, 'abn')

    def test_numeric_user_name_is_kept_as_text(self):
        self.assertEqual(self.analysis('123').USER, '123')

    def test_blank_user_selects_the_project_wide_view(self):
        analysis = self.analysis('   ')
        self.assertEqual(analysis.USER, '')
        self.assertFalse(analysis.USER)

    def test_user_called_null_is_treated_as_a_user_name(self):
        """
        DEFECT: `--user null` is silently ignored and the project-wide view is
        shown, because config.get_parameter converts the text 'null' to None.
        Expected: the name is looked up like any other (and reported as not
        found if it has no activity).
        """
        self.assertEqual(self.analysis('null').USER, 'null')


# -------------------------------------------------------------- _aggregate

class TestAggregate(AnalysisTestCase):

    def test_no_issues_gives_empty_table(self):
        self.assertTrue(self.analysis()._aggregate([]).empty)

    def test_only_uncounted_event_types_gives_empty_table(self):
        issues = [make_issue(1, 'carol', events=[make_event('subscribed', 'dave'),
                                                 make_event('mentioned', 'erin')])]
        self.assertTrue(self.analysis()._aggregate(issues).empty)

    def test_counts_per_contributor(self):
        activity = self.analysis()._aggregate(sample_issues())
        self.assertEqual(list(activity.index), ['alice', 'bob'])
        self.assertEqual(activity.index.name, 'contributor')
        alice, bob = activity.loc['alice'], activity.loc['bob']
        self.assertEqual((alice['comments'], alice['label_actions'], alice['closes']), (2, 2, 1))
        self.assertEqual((bob['comments'], bob['label_actions'], bob['closes']), (2, 0, 0))

    def test_derived_columns(self):
        activity = self.analysis()._aggregate(sample_issues())
        alice = activity.loc['alice']
        self.assertEqual(alice['triage_actions'], 3)
        self.assertEqual(alice['total'], 5)
        self.assertEqual(alice['issues_touched'], 2)
        self.assertEqual(activity.loc['bob', 'total'], 2)

    def test_labeled_and_unlabeled_both_count_as_label_actions(self):
        issues = [make_issue(1, 'carol', events=[make_event('labeled', 'alice'),
                                                 make_event('unlabeled', 'alice')])]
        activity = self.analysis()._aggregate(issues)
        self.assertEqual(activity.loc['alice', 'label_actions'], 2)

    def test_bots_and_unknown_authors_are_excluded(self):
        issues = [make_issue(1, 'carol', events=[
            make_event('commented', 'github-actions[bot]'),
            make_event('closed', 'stale[bot]'),
            make_event('commented', None),
            make_event('commented', ''),
            make_event('commented', 'alice'),
        ])]
        activity = self.analysis()._aggregate(issues)
        self.assertEqual(list(activity.index), ['alice'])

    def test_reporters_own_label_and_close_are_not_triage(self):
        issues = [make_issue(1, 'carol', events=[
            make_event('labeled', 'carol'),
            make_event('unlabeled', 'carol'),
            make_event('closed', 'carol'),
        ])]
        self.assertTrue(self.analysis()._aggregate(issues).empty)

    def test_reporters_own_comments_are_counted(self):
        issues = [make_issue(1, 'carol', events=[make_event('commented', 'carol'),
                                                 make_event('closed', 'carol')])]
        activity = self.analysis()._aggregate(issues)
        self.assertEqual(activity.loc['carol', 'comments'], 1)
        self.assertEqual(activity.loc['carol', 'closes'], 0)

    def test_missing_measures_are_filled_with_zero(self):
        issues = [make_issue(1, 'carol', events=[make_event('commented', 'alice')])]
        activity = self.analysis()._aggregate(issues)
        for column in ('comments', 'label_actions', 'closes',
                       'issues_touched', 'triage_actions', 'total'):
            self.assertIn(column, activity.columns)
        self.assertEqual(activity.loc['alice', 'label_actions'], 0)
        self.assertEqual(activity.loc['alice', 'closes'], 0)

    def test_issues_touched_counts_each_issue_once(self):
        issues = [
            make_issue(1, 'carol', events=[make_event('commented', 'alice')] * 3),
            make_issue(2, 'carol', events=[make_event('commented', 'alice')]),
        ]
        activity = self.analysis()._aggregate(issues)
        self.assertEqual(activity.loc['alice', 'comments'], 4)
        self.assertEqual(activity.loc['alice', 'issues_touched'], 2)

    def test_sorted_by_total_activity(self):
        issues = [make_issue(1, 'carol', events=[
            make_event('commented', 'low'),
            make_event('commented', 'high'), make_event('labeled', 'high'),
            make_event('closed', 'high'),
            make_event('commented', 'mid'), make_event('commented', 'mid'),
        ])]
        activity = self.analysis()._aggregate(issues)
        self.assertEqual(list(activity.index), ['high', 'mid', 'low'])
        self.assertEqual(list(activity['total']), [3, 2, 1])


# -------------------------------------------------------- _first_responses

class TestFirstResponses(AnalysisTestCase):

    def test_no_issues_gives_empty_table_with_columns(self):
        first = self.analysis()._first_responses([])
        self.assertTrue(first.empty)
        self.assertEqual(list(first.columns), ['issue', 'year', 'responder'])

    def test_earliest_reply_wins_even_if_listed_later(self):
        first = self.analysis()._first_responses(sample_issues())
        self.assertEqual(first.set_index('issue')['responder'].to_dict(), {1: 'alice', 2: 'alice'})

    def test_reporter_bots_and_undated_comments_are_not_replies(self):
        issue = make_issue(1, 'carol', events=[
            make_event('commented', 'carol', '2024-01-01T01:00:00Z'),
            make_event('commented', 'github-actions[bot]', '2024-01-01T02:00:00Z'),
            make_event('commented', 'alice', None),
            make_event('labeled', 'dave', '2024-01-01T03:00:00Z'),
            make_event('commented', 'bob', '2024-01-05T00:00:00Z'),
        ])
        first = self.analysis()._first_responses([issue])
        self.assertEqual(list(first['responder']), ['bob'])

    def test_issue_without_any_reply_is_left_out(self):
        issue = make_issue(1, 'carol', events=[make_event('commented', 'carol')])
        self.assertTrue(self.analysis()._first_responses([issue]).empty)

    def test_issue_without_creation_date_is_left_out(self):
        issue = make_issue(1, 'carol', created=None, events=[make_event('commented', 'alice')])
        self.assertTrue(self.analysis()._first_responses([issue]).empty)

    def test_year_is_the_utc_year_the_issue_was_opened(self):
        issues = [
            make_issue(1, 'carol', created='2022-06-01T00:00:00Z',
                       events=[make_event('commented', 'alice', '2024-01-01T00:00:00Z')]),
            # 23:30 on 31 Dec 2023 in UTC-5 is already 2024 in UTC
            make_issue(2, 'carol', created='2023-12-31T23:30:00-05:00',
                       events=[make_event('commented', 'alice', '2024-01-02T00:00:00Z')]),
        ]
        first = self.analysis()._first_responses(issues)
        self.assertEqual(first.set_index('issue')['year'].to_dict(), {1: 2022, 2: 2024})


# --------------------------------------------------- _yearly_concentration

class TestYearlyConcentration(AnalysisTestCase):

    def test_empty_input_gives_empty_table(self):
        self.assertTrue(self.analysis()._yearly_concentration(make_first([])).empty)

    def test_year_needs_at_least_ten_answered_issues(self):
        first = make_first([(2022, 'alice', 9), (2023, 'alice', 10)])
        yearly = self.analysis()._yearly_concentration(first)
        self.assertEqual(list(yearly.index), [2023])

    def test_shares_of_the_top_responders(self):
        first = make_first([(2023, 'alice', 5), (2023, 'bob', 3), (2023, 'carol', 2), (2023, 'dave', 2)])
        row = self.analysis()._yearly_concentration(first).loc[2023]
        self.assertEqual(row['issues'], 12)
        self.assertEqual(row['top_responder'], 'alice')
        self.assertEqual(row['top1_share'], 41.7)
        self.assertEqual(row['top3_share'], 83.3)
        self.assertEqual(row['responders'], 4)


# ----------------------------------------------------------- console output

ACTIVITY = {'alice': (12, 3, 1, 5), 'bob': (10, 0, 0, 4), 'carol': (0, 2, 0, 1)}


class TestPrintSummary(AnalysisTestCase):

    def test_summary_counts_and_table(self):
        printed, _ = self.capture(self.analysis()._print_summary, make_activity(ACTIVITY))
        self.assertIn('3 human contributors with activity; 2 commented, '
                      '1 of those also labeled or closed issues.', printed)
        self.assertIn('Top 10 contributors by total activity:', printed)
        for name in ACTIVITY:
            self.assertIn(name, printed)

    def test_table_is_limited_to_the_top_ten(self):
        rows = {f'user{n:02d}': (20 - n, 0, 0, 1) for n in range(12)}
        printed, _ = self.capture(self.analysis()._print_summary, make_activity(rows))
        self.assertIn('user09', printed)
        self.assertNotIn('user10', printed)
        self.assertNotIn('user11', printed)


class TestPrintCorrelations(AnalysisTestCase):

    def test_too_few_active_contributors(self):
        activity = make_activity({'alice': (12, 3, 1, 5), 'bob': (1, 0, 0, 1)})
        printed, _ = self.capture(self.analysis()._print_correlations, activity)
        self.assertIn('Not enough active contributors to calculate correlations.', printed)

    def test_correlations_are_printed_for_active_contributors(self):
        activity = make_activity({'a': (10, 5, 0, 1), 'b': (8, 3, 0, 1), 'c': (6, 1, 0, 1),
                                  'inactive': (1, 0, 0, 1)})
        printed, _ = self.capture(self.analysis()._print_correlations, activity)
        self.assertIn('(contributors with >= 5 events, n=3)', printed)
        self.assertRegex(printed, r'comments vs label_actions\s+\+1\.00')
        self.assertRegex(printed, r'comments vs triage_actions\s+\+1\.00')

    def test_measure_without_variation_is_shown_as_not_available(self):
        activity = make_activity({'a': (10, 5, 0, 1), 'b': (8, 3, 0, 1), 'c': (6, 1, 0, 1)})
        printed, _ = self.capture(self.analysis()._print_correlations, activity)
        self.assertRegex(printed, r'comments vs closes\s+n/a')


class TestPrintFinding(AnalysisTestCase):

    def finding(self, rows):
        printed, _ = self.capture(self.analysis()._print_finding, make_activity(rows))
        self.assertIn('FINDING:', printed)
        return printed

    def test_frequent_and_occasional_commenters_are_compared(self):
        printed = self.finding({'alice': (12, 3, 1, 5), 'bob': (10, 0, 0, 4),
                                'carol': (2, 0, 0, 1), 'dave': (1, 1, 0, 1), 'erin': (3, 0, 0, 1)})
        self.assertIn('50.0% of frequent commenters (>= 10 comments, n=2) also label or close '
                      'issues, compared with 33.3% of occasional commenters (n=3).', printed)

    def test_no_comparison_without_frequent_commenters(self):
        printed = self.finding({'carol': (2, 0, 0, 1), 'dave': (1, 1, 0, 1)})
        self.assertNotIn('frequent commenters', printed)

    def test_positive_relationship(self):
        printed = self.finding({'a': (10, 5, 0, 1), 'b': (8, 3, 0, 1), 'c': (6, 1, 0, 1)})
        self.assertIn('people who comment more also triage more (rank correlation +1.00)', printed)

    def test_negative_relationship(self):
        printed = self.finding({'a': (10, 0, 0, 1), 'b': (8, 2, 0, 1), 'c': (6, 5, 0, 1)})
        self.assertIn('people who comment more tend to triage less (rank correlation -1.00)', printed)

    def test_weak_relationship(self):
        printed = self.finding({'w': (5, 2, 0, 1), 'x': (6, 4, 0, 1),
                                'y': (7, 1, 0, 1), 'z': (8, 3, 0, 1)})
        self.assertIn('commenting volume and triage work are only weakly related', printed)

    def test_no_relationship_line_when_correlation_is_undefined(self):
        printed = self.finding({'a': (5, 1, 0, 1), 'b': (5, 2, 0, 1)})
        self.assertNotIn('Among active contributors', printed)

    def test_no_relationship_line_with_fewer_than_two_active_contributors(self):
        printed = self.finding({'a': (5, 1, 0, 1), 'b': (1, 0, 0, 1)})
        self.assertNotIn('Among active contributors', printed)

    def test_share_of_the_top_ten(self):
        rows = {f'top{n}': (9, 0, 0, 1) for n in range(10)}
        rows.update({'small1': (5, 0, 0, 1), 'small2': (5, 0, 0, 1)})
        printed = self.finding(rows)
        self.assertIn('The top 10 contributors account for 90% of all counted activity.', printed)


class TestPrintResponders(AnalysisTestCase):

    def test_no_replies(self):
        printed, _ = self.capture(self.analysis()._print_responders, make_first([]))
        self.assertIn('No issue received a reply from someone other than its reporter.', printed)
        self.assertNotIn('FINDING', printed)

    def test_concentration_over_two_years(self):
        first = make_first([(2022, 'alice', 8), (2022, 'bob', 2), (2023, 'bob', 7), (2023, 'alice', 3)])
        printed, _ = self.capture(self.analysis()._print_responders, first)
        self.assertIn('20 issues got a first reply from someone other than the reporter, '
                      'from 2 different people.', printed)
        self.assertIn('Top responder: alice (55%); top 3: 100%; top 10: 100%.', printed)
        self.assertIn('distinct responders', printed)
        self.assertIn('FINDING: alice wrote the first reply on 55% of answered issues', printed)
        self.assertIn("The top responder's share went from 80% in 2022 to 70% in 2023", printed)

    def test_single_year_has_no_trend_sentence(self):
        first = make_first([(2023, 'alice', 6), (2023, 'bob', 4)])
        printed, _ = self.capture(self.analysis()._print_responders, first)
        self.assertIn('distinct responders', printed)
        self.assertNotIn('went from', printed)

    def test_years_with_few_answers_have_no_yearly_table(self):
        first = make_first([(2023, 'alice', 2), (2024, 'bob', 1)])
        printed, _ = self.capture(self.analysis()._print_responders, first)
        self.assertIn('Top responder: alice (67%)', printed)
        self.assertNotIn('distinct responders', printed)
        self.assertNotIn('went from', printed)


class TestPrintUserSummary(AnalysisTestCase):

    FIRST = [(2024, 'alice', 3), (2024, 'bob', 1)]

    def summary(self, user, rows=None, first=None):
        analysis = self.analysis(user)
        activity = make_activity(rows or ACTIVITY)
        first = make_first(self.FIRST if first is None else first)
        printed, found = self.capture(analysis._print_user_summary, activity, first)
        return analysis, printed, found

    def test_existing_user_is_reported(self):
        analysis, printed, found = self.summary('alice')
        self.assertTrue(found)
        self.assertIn('Contributor: alice', printed)
        self.assertIn('Comments:        12', printed)
        self.assertIn('Label actions:   3', printed)
        self.assertIn('Issues closed:   1', printed)
        self.assertIn('Issues touched:  5', printed)
        self.assertIn('Overall rank:    #1 of 3 contributors (57.1% of all activity)', printed)
        self.assertIn('First replies:   3 (75.0% of 4 first replies to issues)', printed)
        self.assertIn("25% of alice's activity is triage (labeling/closing) versus "
                      '21% for the top 10 contributors overall.', printed)

    def test_user_lookup_ignores_case_and_keeps_the_real_spelling(self):
        analysis, printed, found = self.summary('ALICE')
        self.assertTrue(found)
        self.assertEqual(analysis.USER, 'alice')
        self.assertIn('Contributor: alice', printed)

    def test_contributors_with_equal_activity_share_a_rank(self):
        rows = dict(ACTIVITY, dan=(10, 0, 0, 2))
        for user in ('bob', 'dan'):
            _, printed, _ = self.summary(user, rows=rows)
            self.assertIn('Overall rank:    #2 of 4 contributors', printed)

    def test_no_first_reply_line_without_first_replies(self):
        _, printed, found = self.summary('alice', first=[])
        self.assertTrue(found)
        self.assertNotIn('First replies', printed)

    def test_unknown_user_gets_suggestions(self):
        analysis, printed, found = self.summary('alise')
        self.assertFalse(found)
        self.assertIn('No activity found for user "alise" (bots are excluded).', printed)
        self.assertIn('Did you mean: alice?', printed)
        self.assertNotIn('Contributor:', printed)

    def test_unknown_user_without_similar_name_gets_most_active_list(self):
        _, printed, found = self.summary('zzzzqqqq')
        self.assertFalse(found)
        self.assertIn('Most active contributors: alice, bob, carol', printed)
        self.assertNotIn('Did you mean', printed)


# ------------------------------------------------------------------- charts

class TestPlotActivity(AnalysisTestCase):

    def test_project_view_has_three_bars_per_contributor(self):
        self.analysis()._plot_activity(make_activity(ACTIVITY))
        self.show.assert_called_once()
        ax = plt.gcf().axes[0]
        self.assertEqual(ax.get_title(), 'Activity of the top 10 contributors (bots excluded)')
        self.assertEqual(ax.get_xlabel(), 'Contributor')
        self.assertEqual(ax.get_ylabel(), 'Number of events')
        self.assertEqual([t.get_text() for t in ax.get_xticklabels()], ['alice', 'bob', 'carol'])
        self.assertEqual(len(ax.patches), 9)
        self.assertEqual([t.get_text() for t in ax.get_legend().get_texts()],
                         ['Comments', 'Label actions', 'Issues closed'])

    def test_project_view_is_limited_to_the_top_ten(self):
        rows = {f'user{n:02d}': (20 - n, 1, 0, 1) for n in range(12)}
        self.analysis()._plot_activity(make_activity(rows))
        ax = plt.gcf().axes[0]
        self.assertEqual(len(ax.get_xticklabels()), 10)
        self.assertEqual(len(ax.patches), 30)

    def test_user_view_compares_the_user_with_the_top_average(self):
        analysis = self.analysis('bob')
        analysis._plot_activity(make_activity(ACTIVITY))
        self.show.assert_called_once()
        ax = plt.gcf().axes[0]
        self.assertEqual(ax.get_title(), 'Activity of bob compared with the top 10 contributors')
        self.assertEqual([t.get_text() for t in ax.get_xticklabels()], ['bob', 'Average of top 10'])
        comment_bars = ax.patches[:2]
        self.assertAlmostEqual(comment_bars[0].get_height(), 10)
        self.assertAlmostEqual(comment_bars[1].get_height(), (12 + 10 + 0) / 3)


class TestPlotRelationship(AnalysisTestCase):

    def test_scatter_separates_triagers_from_comment_only_contributors(self):
        self.analysis()._plot_relationship(make_activity(ACTIVITY))
        self.show.assert_called_once()
        ax = plt.gcf().axes[0]
        self.assertEqual(ax.get_title(), 'Do frequent commenters also triage issues?')
        self.assertEqual(ax.get_xscale(), 'symlog')
        self.assertEqual(ax.get_yscale(), 'symlog')
        self.assertEqual([t.get_text() for t in ax.get_legend().get_texts()],
                         ['Comments only (1)', 'Also label/close issues (2)'])
        self.assertEqual({t.get_text() for t in ax.texts}, {'alice', 'bob', 'carol'})


class TestPlotResponders(AnalysisTestCase):

    def test_no_chart_when_no_year_has_enough_answers(self):
        self.analysis()._plot_responders(make_first([(2024, 'alice', 3)]))
        self.show.assert_not_called()
        self.assertEqual(plt.get_fignums(), [])

    def test_chart_shows_top_one_and_top_three_share_per_year(self):
        first = make_first([(2022, 'alice', 8), (2022, 'bob', 2), (2023, 'bob', 7), (2023, 'alice', 3)])
        self.analysis()._plot_responders(first)
        self.show.assert_called_once()
        ax = plt.gcf().axes[0]
        self.assertEqual(ax.get_title(), 'How concentrated are first replies on a few people?')
        self.assertEqual(ax.get_ylabel(), '% of first replies')
        self.assertEqual(ax.get_ylim(), (0, 105))
        self.assertEqual(list(ax.get_xticks()), [2022, 2023])
        top1, top3 = ax.lines
        self.assertEqual(list(top1.get_ydata()), [80.0, 70.0])
        self.assertEqual(list(top3.get_ydata()), [100.0, 100.0])
        self.assertEqual({t.get_text() for t in ax.texts}, {'alice (n=10)', 'bob (n=10)'})


# ---------------------------------------------------------------------- run

class TestRun(AnalysisTestCase):

    def test_question_and_method_are_printed(self):
        printed = self.run_with(sample_issues())
        self.assertIn('QUESTION:', printed)
        self.assertIn('METHOD:', printed)

    def test_no_activity_stops_before_any_chart(self):
        printed = self.run_with([])
        self.assertIn('No contributor activity found.', printed)
        self.show.assert_not_called()

    def test_project_view_prints_all_sections(self):
        printed = self.run_with(sample_issues())
        self.assertIn('2 human contributors with activity', printed)
        self.assertIn('Not enough active contributors to calculate correlations.', printed)
        self.assertIn('FINDING:', printed)
        self.assertIn('FIRST-REPLY CONCENTRATION', printed)
        self.assertIn('2 issues got a first reply', printed)
        # activity chart + scatter plot; no yearly chart (fewer than 10 answered issues)
        self.assertEqual(self.show.call_count, 2)

    def test_project_view_shows_three_charts_with_enough_data(self):
        printed = self.run_with(busy_year_issues(10))
        self.assertIn('Top responder: alice (100%)', printed)
        self.assertEqual(self.show.call_count, 3)

    def test_single_contributor_skips_the_scatter_plot(self):
        issues = [make_issue(1, 'carol', events=[make_event('commented', 'alice')])]
        self.run_with(issues)
        self.assertEqual(self.show.call_count, 1)

    def test_no_replies_skips_the_yearly_chart(self):
        issues = [make_issue(1, 'carol', events=[make_event('commented', 'carol'),
                                                 make_event('labeled', 'alice')])]
        printed = self.run_with(issues)
        self.assertIn('No issue received a reply', printed)
        self.assertEqual(self.show.call_count, 2)

    def test_user_view_shows_one_chart(self):
        printed = self.run_with(sample_issues(), user='ALICE')
        self.assertIn('Contributor: alice', printed)
        self.assertIn('First replies:   2 (100.0% of 2 first replies to issues)', printed)
        self.assertNotIn('Top 10 contributors by total activity', printed)
        self.assertNotIn('FIRST-REPLY CONCENTRATION', printed)
        self.assertEqual(self.show.call_count, 1)

    def test_unknown_user_ends_without_a_chart(self):
        printed = self.run_with(sample_issues(), user='nobody-here')
        self.assertIn('No activity found for user "nobody-here"', printed)
        self.show.assert_not_called()

    def test_bot_name_is_reported_as_not_found(self):
        printed = self.run_with(sample_issues(), user='github-actions[bot]')
        self.assertIn('No activity found for user "github-actions[bot]" (bots are excluded).', printed)
        self.show.assert_not_called()

    def test_missing_data_file_gives_a_message_instead_of_a_crash(self):
        """
        DEFECT: the README says "If the path is missing or wrong, the
        application prints a clear error message instead of crashing", but
        feature 2 ends with an uncaught FileNotFoundError and a stack trace.
        """
        os.environ['ENPM611_PROJECT_DATA_PATH'] = os.path.join('no', 'such', 'file.json')
        self.addCleanup(setattr, data_loader, '_ISSUES', data_loader._ISSUES)
        data_loader._ISSUES = None
        analysis = self.analysis()
        crash = None
        try:
            self.capture(analysis.run)
        except FileNotFoundError as error:
            crash = error
        self.assertIsNone(crash, 'run() crashed with an uncaught FileNotFoundError')

    def test_module_can_be_run_as_a_script(self):
        with mock.patch.object(data_loader.DataLoader, 'get_issues', return_value=[]):
            printed, _ = self.capture(
                lambda: runpy.run_path(caa.__file__, run_name='__main__'))
        self.assertIn('No contributor activity found.', printed)


if __name__ == '__main__':
    unittest.main()
