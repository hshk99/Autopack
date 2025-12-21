import pytest
import requests
from unittest.mock import patch
from src.autopack.research.gatherers.github_gatherer import GitHubGatherer

@patch('src.autopack.research.gatherers.github_gatherer.requests.get')
def test_fetch_repository_data_success(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {'name': 'repo'}

    gatherer = GitHubGatherer(token='fake_token')
    data = gatherer.fetch_repository_data('owner/repo')

    assert data['name'] == 'repo'
    mock_get.assert_called_once_with(
        'https://api.github.com/repos/owner/repo',
        headers={'Authorization': 'token fake_token', 'Accept': 'application/vnd.github.v3+json'}
    )

@patch('src.autopack.research.gatherers.github_gatherer.requests.get')
def test_fetch_repository_data_failure(mock_get):
    mock_get.return_value.status_code = 404
    mock_get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError

    gatherer = GitHubGatherer(token='fake_token')
    data = gatherer.fetch_repository_data('owner/repo')

    assert data is None
    assert mock_get.call_count == 3  # Retries 3 times

@patch('src.autopack.research.gatherers.github_gatherer.requests.get')
def test_fetch_repository_data_partial_failure(mock_get):
    responses = [
        requests.Response(),
        requests.Response(),
        requests.Response()
    ]
    responses[0].status_code = 500
    responses[1].status_code = 500
    responses[2].status_code = 200
    responses[2]._content = b'{"name": "repo"}'

    mock_get.side_effect = responses

    gatherer = GitHubGatherer(token='fake_token')
    data = gatherer.fetch_repository_data('owner/repo')

    assert data['name'] == 'repo'
