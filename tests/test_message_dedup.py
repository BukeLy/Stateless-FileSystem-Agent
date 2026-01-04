"""Test message deduplication logic for SDK client."""
from unittest.mock import MagicMock, patch

import pytest

from config import Config
from handler import is_message_duplicate


@pytest.fixture
def mock_config():
    """Create a mock config with dedup table."""
    return Config(
        telegram_token='test-token',
        agent_server_url='https://test.example.com',
        auth_token='test-auth',
        message_dedup_table='test-dedup-table',
    )


@pytest.fixture
def mock_config_no_table():
    """Create a mock config without dedup table."""
    return Config(
        telegram_token='test-token',
        agent_server_url='https://test.example.com',
        auth_token='test-auth',
        message_dedup_table='',
    )


class TestIsDuplicateMessage:
    """Tests for is_message_duplicate function."""

    def test_no_table_configured_returns_false(self, mock_config_no_table):
        """When no dedup table is configured, should return False."""
        result = is_message_duplicate(mock_config_no_table, 12345, 67890)
        assert result is False

    @patch('handler._get_dynamodb_resource')
    def test_new_message_returns_false(self, mock_get_dynamodb, mock_config):
        """First occurrence of a message should return False."""
        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        # Simulate successful put (no exception)
        mock_table.put_item.return_value = {}

        result = is_message_duplicate(mock_config, 12345, 67890)

        assert result is False
        mock_table.put_item.assert_called_once()
        # Verify the key format
        call_args = mock_table.put_item.call_args
        assert call_args[1]['Item']['message_key'] == '12345:67890'

    @patch('handler._get_dynamodb_resource')
    def test_duplicate_message_returns_true(self, mock_get_dynamodb, mock_config):
        """Duplicate message should return True."""
        from botocore.exceptions import ClientError

        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        # Simulate ConditionalCheckFailedException
        mock_table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException'}},
            'PutItem'
        )

        result = is_message_duplicate(mock_config, 12345, 67890)

        assert result is True

    @patch('handler._get_dynamodb_resource')
    def test_other_dynamo_error_raises(self, mock_get_dynamodb, mock_config):
        """Other DynamoDB errors should be re-raised."""
        from botocore.exceptions import ClientError

        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        # Simulate a different error
        mock_table.put_item.side_effect = ClientError(
            {'Error': {'Code': 'ProvisionedThroughputExceededException'}},
            'PutItem'
        )

        with pytest.raises(ClientError):
            is_message_duplicate(mock_config, 12345, 67890)

    @patch('handler._get_dynamodb_resource')
    @patch('handler.time')
    def test_ttl_is_24_hours(self, mock_time, mock_get_dynamodb, mock_config):
        """TTL should be set to 24 hours from current time."""
        mock_time.time.return_value = 1000000
        mock_table = MagicMock()
        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table
        mock_get_dynamodb.return_value = mock_dynamodb
        mock_table.put_item.return_value = {}

        is_message_duplicate(mock_config, 12345, 67890)

        call_args = mock_table.put_item.call_args
        item = call_args[1]['Item']
        assert item['created_at'] == 1000000
        assert item['ttl'] == 1000000 + 86400  # 24 hours


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
