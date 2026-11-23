"""
Unit tests for model.py (Team 1 application, tested by Team 4).

Covers the Event and Issue classes, the State enum and the _as_utc helper,
including the derived values closed_date, days_to_close and human_comments.
All test data is built in memory.
"""

import unittest
from datetime import datetime, timedelta, timezone

from model import Event, Issue, State, _as_utc


def event_json(event_type='commented', author='alice', date='2024-01-02T00:00:00Z', **extra):
    jobj = {'event_type': event_type, 'author': author, 'event_date': date}
    jobj.update(extra)
    return jobj


def issue_json(**overrides):
    jobj = {
        'url': 'https://github.com/python-poetry/poetry/issues/7',
        'creator': 'reporter',
        'labels': ['kind/bug', 'status/triage'],
        'state': 'closed',
        'assignees': ['alice'],
        'title': 'Something is broken',
        'text': 'Details',
        'number': 7,
        'created_date': '2024-01-01T00:00:00Z',
        'updated_date': '2024-01-05T00:00:00Z',
        'timeline_url': 'https://api.github.com/issues/7/timeline',
        'events': [],
    }
    jobj.update(overrides)
    return jobj


class TestAsUtc(unittest.TestCase):

    def test_none_stays_none(self):
        self.assertIsNone(_as_utc(None))

    def test_naive_datetime_is_treated_as_utc(self):
        result = _as_utc(datetime(2024, 1, 1, 12, 0))
        self.assertEqual(result, datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc))

    def test_aware_datetime_is_converted_to_utc(self):
        eastern = timezone(timedelta(hours=-5))
        result = _as_utc(datetime(2024, 1, 1, 20, 0, tzinfo=eastern))
        self.assertEqual(result.utcoffset(), timedelta(0))
        self.assertEqual((result.day, result.hour), (2, 1))


class TestState(unittest.TestCase):

    def test_states_compare_equal_to_their_text(self):
        self.assertEqual(State.open, 'open')
        self.assertEqual(State.closed, 'closed')
        self.assertIs(State['closed'], State.closed)


class TestEvent(unittest.TestCase):

    def test_event_without_json_has_empty_fields(self):
        event = Event(None)
        self.assertIsNone(event.event_type)
        self.assertIsNone(event.author)
        self.assertIsNone(event.event_date)
        self.assertIsNone(event.label)
        self.assertIsNone(event.comment)

    def test_event_reads_all_fields(self):
        event = Event(event_json('labeled', 'alice', '2024-03-04T05:06:07Z',
                                 label='kind/bug', comment='text'))
        self.assertEqual(event.event_type, 'labeled')
        self.assertEqual(event.author, 'alice')
        self.assertEqual(event.event_date, datetime(2024, 3, 4, 5, 6, 7, tzinfo=timezone.utc))
        self.assertEqual(event.label, 'kind/bug')
        self.assertEqual(event.comment, 'text')

    def test_missing_or_invalid_date_becomes_none(self):
        self.assertIsNone(Event({'event_type': 'commented', 'author': 'alice'}).event_date)
        self.assertIsNone(Event(event_json(date='not a date')).event_date)

    def test_real_user_is_human(self):
        self.assertTrue(Event(event_json(author='alice')).is_human)

    def test_bot_is_not_human(self):
        self.assertFalse(Event(event_json(author='github-actions[bot]')).is_human)

    def test_unknown_author_is_not_human(self):
        self.assertFalse(Event(event_json(author=None)).is_human)
        self.assertFalse(Event(event_json(author='')).is_human)


class TestIssue(unittest.TestCase):

    def test_issue_without_json_has_defaults(self):
        issue = Issue()
        self.assertIsNone(issue.url)
        self.assertIsNone(issue.creator)
        self.assertEqual(issue.labels, [])
        self.assertIsNone(issue.state)
        self.assertEqual(issue.assignees, [])
        self.assertEqual(issue.number, -1)
        self.assertIsNone(issue.created_date)
        self.assertIsNone(issue.updated_date)
        self.assertEqual(issue.events, [])

    def test_issue_reads_all_fields(self):
        issue = Issue(issue_json(events=[event_json(), event_json('closed')]))
        self.assertEqual(issue.url, 'https://github.com/python-poetry/poetry/issues/7')
        self.assertEqual(issue.creator, 'reporter')
        self.assertEqual(issue.labels, ['kind/bug', 'status/triage'])
        self.assertIs(issue.state, State.closed)
        self.assertEqual(issue.assignees, ['alice'])
        self.assertEqual(issue.title, 'Something is broken')
        self.assertEqual(issue.text, 'Details')
        self.assertEqual(issue.number, 7)
        self.assertEqual(issue.created_date, datetime(2024, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(issue.updated_date, datetime(2024, 1, 5, tzinfo=timezone.utc))
        self.assertEqual(issue.timeline_url, 'https://api.github.com/issues/7/timeline')
        self.assertEqual(len(issue.events), 2)
        self.assertTrue(all(isinstance(e, Event) for e in issue.events))

    def test_number_given_as_text_is_converted(self):
        self.assertEqual(Issue(issue_json(number='123')).number, 123)

    def test_invalid_number_keeps_default(self):
        self.assertEqual(Issue(issue_json(number='abc')).number, -1)
        self.assertEqual(Issue(issue_json(number=None)).number, -1)

    def test_invalid_dates_become_none(self):
        issue = Issue(issue_json(created_date='garbage', updated_date=None))
        self.assertIsNone(issue.created_date)
        self.assertIsNone(issue.updated_date)

    def test_missing_lists_default_to_empty(self):
        issue = Issue({'state': 'open'})
        self.assertEqual(issue.labels, [])
        self.assertEqual(issue.assignees, [])
        self.assertEqual(issue.events, [])
        self.assertEqual(issue.number, -1)

    def test_issue_without_state_can_still_be_loaded(self):
        """
        DEFECT: a record with no 'state' crashes with KeyError(None), although
        a missing number or date is tolerated. One incomplete record makes the
        whole data file unloadable.
        """
        jobj = issue_json()
        del jobj['state']
        issue, crash = None, None
        try:
            issue = Issue(jobj)
        except KeyError as error:
            crash = error
        self.assertIsNone(crash, 'Issue without a state raised a KeyError instead of loading')
        self.assertIsNone(issue.state)
        self.assertEqual(issue.number, 7)


class TestClosedDate(unittest.TestCase):

    def test_no_closed_event_gives_none(self):
        issue = Issue(issue_json(events=[event_json('commented')]))
        self.assertIsNone(issue.closed_date)

    def test_latest_closed_event_is_used_for_reopened_issues(self):
        issue = Issue(issue_json(events=[
            event_json('closed', date='2024-01-03T00:00:00Z'),
            event_json('reopened', date='2024-01-04T00:00:00Z'),
            event_json('closed', date='2024-01-09T00:00:00Z'),
            event_json('closed', date='2024-01-06T00:00:00Z'),
        ]))
        self.assertEqual(issue.closed_date, datetime(2024, 1, 9, tzinfo=timezone.utc))

    def test_closed_event_without_date_is_ignored(self):
        issue = Issue(issue_json(events=[event_json('closed', date=None)]))
        self.assertIsNone(issue.closed_date)

    def test_dates_with_and_without_timezone_can_be_compared(self):
        issue = Issue(issue_json(events=[
            event_json('closed', date='2024-01-03T00:00:00'),
            event_json('closed', date='2024-01-02T23:00:00-05:00'),
        ]))
        self.assertEqual(issue.closed_date, datetime(2024, 1, 3, 4, 0, tzinfo=timezone.utc))


class TestDaysToClose(unittest.TestCase):

    def test_days_between_creation_and_closing(self):
        issue = Issue(issue_json(events=[event_json('closed', date='2024-01-03T12:00:00Z')]))
        self.assertAlmostEqual(issue.days_to_close(), 2.5)

    def test_closed_in_the_same_moment_is_zero_days(self):
        issue = Issue(issue_json(events=[event_json('closed', date='2024-01-01T00:00:00Z')]))
        self.assertEqual(issue.days_to_close(), 0)

    def test_open_issue_has_no_days_to_close(self):
        issue = Issue(issue_json(state='open',
                                 events=[event_json('closed', date='2024-01-03T00:00:00Z')]))
        self.assertIsNone(issue.days_to_close())

    def test_closed_issue_without_closed_event_has_no_days_to_close(self):
        self.assertIsNone(Issue(issue_json(events=[])).days_to_close())

    def test_missing_creation_date_has_no_days_to_close(self):
        issue = Issue(issue_json(created_date=None,
                                 events=[event_json('closed', date='2024-01-03T00:00:00Z')]))
        self.assertIsNone(issue.days_to_close())

    def test_closing_before_creation_is_rejected(self):
        issue = Issue(issue_json(events=[event_json('closed', date='2023-12-25T00:00:00Z')]))
        self.assertIsNone(issue.days_to_close())


class TestHumanComments(unittest.TestCase):

    def test_only_comments_by_real_users_are_returned(self):
        issue = Issue(issue_json(events=[
            event_json('commented', 'alice'),
            event_json('commented', 'github-actions[bot]'),
            event_json('commented', None),
            event_json('labeled', 'bob'),
            event_json('commented', 'bob'),
        ]))
        self.assertEqual([e.author for e in issue.human_comments()], ['alice', 'bob'])

    def test_issue_without_events_has_no_comments(self):
        self.assertEqual(Issue(issue_json()).human_comments(), [])


if __name__ == '__main__':
    unittest.main()
