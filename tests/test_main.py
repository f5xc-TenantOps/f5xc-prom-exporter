"""Tests for main entry point."""

from unittest.mock import Mock, patch

import pytest

from f5xc_exporter import main


class TestMain:
    """Test main module."""

    @patch('f5xc_exporter.main.get_config')
    @patch('f5xc_exporter.main.MetricsServer')
    @patch('f5xc_exporter.main.setup_logging')
    def test_main_success(self, mock_setup_logging, mock_metrics_server, mock_get_config):
        """Test successful main execution."""
        # Mock configuration
        mock_config = Mock()
        mock_config.f5xc_exp_log_level = "INFO"
        mock_config.tenant_url_str = "https://test.console.ves.volterra.io"
        mock_config.f5xc_exp_http_port = 8080
        mock_get_config.return_value = mock_config

        # Mock server
        mock_server = Mock()
        mock_metrics_server.return_value = mock_server
        mock_server.start.side_effect = KeyboardInterrupt()  # Simulate interrupt

        with pytest.raises(SystemExit) as exc_info:
            main.main()

        assert exc_info.value.code == 0  # Normal exit

        mock_setup_logging.assert_called_once_with("INFO")
        mock_metrics_server.assert_called_once_with(mock_config)
        mock_server.start.assert_called_once()

    @patch('f5xc_exporter.main.get_config')
    def test_main_config_error(self, mock_get_config):
        """Test main with configuration error."""
        mock_get_config.side_effect = Exception("Config error")

        with pytest.raises(SystemExit) as exc_info:
            main.main()

        # Should exit with code 1 on config error
        assert exc_info.value.code == 1

    @patch('f5xc_exporter.main.get_config')
    @patch('f5xc_exporter.main.MetricsServer')
    @patch('f5xc_exporter.main.setup_logging')
    def test_main_server_start_error(self, mock_setup_logging, mock_metrics_server, mock_get_config):
        """Test main with server start error."""
        # Mock configuration
        mock_config = Mock()
        mock_config.f5xc_exp_log_level = "INFO"
        mock_config.tenant_url_str = "https://test.console.ves.volterra.io"
        mock_config.f5xc_exp_http_port = 8080
        mock_get_config.return_value = mock_config

        # Mock server to raise error on start
        mock_server = Mock()
        mock_metrics_server.return_value = mock_server
        mock_server.start.side_effect = Exception("Server error")

        with pytest.raises(SystemExit) as exc_info:
            main.main()

        assert exc_info.value.code == 1

    @patch('f5xc_exporter.main.structlog')
    def test_setup_logging(self, mock_structlog):
        """Test logging setup."""
        main.setup_logging("DEBUG")

        mock_structlog.configure.assert_called_once()

        # Check that configure was called with processors
        call_args = mock_structlog.configure.call_args
        assert 'processors' in call_args.kwargs
        assert len(call_args.kwargs['processors']) > 0

    @patch('f5xc_exporter.main.logging')
    def test_setup_logging_level(self, mock_logging):
        """Test logging level setup."""
        main.setup_logging("WARNING")

        # Check that basicConfig was called
        mock_logging.basicConfig.assert_called_once()

        # Check that log level was set correctly
        call_args = mock_logging.basicConfig.call_args
        assert call_args.kwargs['level'] == mock_logging.WARNING

    @patch('f5xc_exporter.main.get_config')
    @patch('f5xc_exporter.main.MetricsServer')
    @patch('f5xc_exporter.main.setup_logging')
    @patch('f5xc_exporter.main.signal')
    def test_signal_handlers(self, mock_signal, mock_setup_logging, mock_metrics_server, mock_get_config):
        """Test signal handler setup."""
        # Mock configuration
        mock_config = Mock()
        mock_config.f5xc_exp_log_level = "INFO"
        mock_config.tenant_url_str = "https://test.console.ves.volterra.io"
        mock_config.f5xc_exp_http_port = 8080
        mock_get_config.return_value = mock_config

        # Mock server
        mock_server = Mock()
        mock_metrics_server.return_value = mock_server
        mock_server.start.side_effect = KeyboardInterrupt()

        with pytest.raises(SystemExit):
            main.main()

        # Check that signal handlers were set up
        assert mock_signal.signal.call_count >= 2  # SIGINT and SIGTERM

        # Check specific signals
        signal_calls = mock_signal.signal.call_args_list
        signals_set = [call[0][0] for call in signal_calls]
        assert mock_signal.SIGINT in signals_set
        assert mock_signal.SIGTERM in signals_set

    @patch('f5xc_exporter.main.get_config')
    @patch('f5xc_exporter.main.MetricsServer')
    @patch('f5xc_exporter.main.setup_logging')
    @patch('f5xc_exporter.main.structlog')
    def test_signal_handler_function(self, mock_structlog, mock_setup_logging, mock_metrics_server, mock_get_config):
        """Test signal handler function behavior."""
        # Mock logger
        mock_logger = Mock()
        mock_structlog.get_logger.return_value = mock_logger

        # Mock configuration
        mock_config = Mock()
        mock_config.f5xc_exp_log_level = "INFO"
        mock_config.tenant_url_str = "https://test.console.ves.volterra.io"
        mock_config.f5xc_exp_http_port = 8080
        mock_get_config.return_value = mock_config

        # Mock server
        mock_server = Mock()
        mock_metrics_server.return_value = mock_server

        # Capture the signal handler function
        with patch('f5xc_exporter.main.signal') as mock_signal:
            try:
                main.main()
            except:
                pass  # We're just testing setup

            # Get the signal handler function
            signal_calls = mock_signal.signal.call_args_list
            sigint_handler = None
            for call in signal_calls:
                if call[0][0] == mock_signal.SIGINT:
                    sigint_handler = call[0][1]
                    break

            assert sigint_handler is not None

            # Test the signal handler
            with pytest.raises(SystemExit) as exc_info:
                sigint_handler(mock_signal.SIGINT, None)

            assert exc_info.value.code == 0
            mock_server.stop.assert_called_once()

    def test_main_entry_point(self):
        """Test that main can be called as entry point."""
        # This is a basic test to ensure the main function exists
        assert callable(main.main)

    @patch('f5xc_exporter.main.main')
    def test_name_main_guard(self, mock_main):
        """Test __name__ == '__main__' guard."""
        # This test verifies the structure but doesn't execute the guard
        # since we can't easily simulate the __name__ == '__main__' condition
        # in a test environment.

        # Just verify main function exists and is callable
        assert hasattr(main, 'main')
        assert callable(main.main)
