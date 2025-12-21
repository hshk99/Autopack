import pytest
from unittest.mock import patch, MagicMock
from src.autopack.research.gatherers.reddit_gatherer import RedditGatherer

@patch('src.autopack.research.gatherers.reddit_gatherer.praw.Reddit')
def test_fetch_subreddit_data_success(mock_reddit):
    mock_subreddit = MagicMock()
    mock_subreddit.hot.return_value = [MagicMock(title='Post 1'), MagicMock(title='Post 2')]
    mock_reddit.return_value.subreddit.return_value = mock_subreddit

    gatherer = RedditGatherer(client_id='fake_id', client_secret='fake_secret', user_agent='fake_agent')
    posts = gatherer.fetch_subreddit_data('python')

    assert len(posts) == 2
    assert posts[0].title == 'Post 1'
    assert posts[1].title == 'Post 2'

@patch('src.autopack.research.gatherers.reddit_gatherer.praw.Reddit')
def test_fetch_subreddit_data_failure(mock_reddit):
    mock_subreddit = MagicMock()
    mock_subreddit.hot.side_effect = Exception("API Error")
    mock_reddit.return_value.subreddit.return_value = mock_subreddit

    gatherer = RedditGatherer(client_id='fake_id', client_secret='fake_secret', user_agent='fake_agent')
    posts = gatherer.fetch_subreddit_data('python')

    assert posts is None

@patch('src.autopack.research.gatherers.reddit_gatherer.praw.Reddit')
def test_fetch_subreddit_data_partial_failure(mock_reddit):
    mock_subreddit = MagicMock()
    attempts = 0

    def side_effect(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 2:
            raise Exception("API Error")
        return [MagicMock(title='Post 1')]

    mock_subreddit.hot.side_effect = side_effect
    mock_reddit.return_value.subreddit.return_value = mock_subreddit

    gatherer = RedditGatherer(client_id='fake_id', client_secret='fake_secret', user_agent='fake_agent')
    posts = gatherer.fetch_subreddit_data('python')

    assert len(posts) == 1
    assert posts[0].title == 'Post 1'
