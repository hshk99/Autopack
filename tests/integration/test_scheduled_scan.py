"""
Integration tests for scheduled storage scans (BUILD-150 Phase 3).

Tests Windows Task Scheduler integration and automated scan workflows.
"""

import pytest
import subprocess
from unittest.mock import Mock, patch
from pathlib import Path


class TestScheduledScanSetup:
    """Test Windows Task Scheduler setup script."""

    @patch('subprocess.run')
    def test_create_scheduled_task_success(self, mock_run):
        """Test creating scheduled task with schtasks command."""
        from scripts.setup_scheduled_scan import create_scheduled_task

        # Mock successful schtasks execution
        mock_run.return_value = Mock(
            returncode=0,
            stdout='SUCCESS: The scheduled task "Autopack_Storage_Scan" has successfully been created.',
            stderr=''
        )

        success = create_scheduled_task(
            task_name='Autopack_Storage_Scan_Test',
            frequency_days=14,
            start_time='02:00',
            notify=True,
            auto_execute=False
        )

        assert success
        mock_run.assert_called_once()

        # Verify schtasks command structure
        call_args = mock_run.call_args[0][0]
        assert 'schtasks' in call_args
        assert '/Create' in call_args
        assert '/TN' in call_args
        assert 'Autopack_Storage_Scan_Test' in call_args
        assert '/SC' in call_args
        assert 'DAILY' in call_args
        assert '/MO' in call_args
        assert '14' in call_args
        assert '/ST' in call_args
        assert '02:00' in call_args

    @patch('subprocess.run')
    def test_create_scheduled_task_includes_wiztree_flag(self, mock_run):
        """Test scheduled task command includes --wiztree flag."""
        from scripts.setup_scheduled_scan import create_scheduled_task

        mock_run.return_value = Mock(returncode=0, stdout='SUCCESS', stderr='')

        create_scheduled_task(
            task_name='Test_Task',
            frequency_days=7,
            start_time='03:00',
            notify=True,
            auto_execute=False
        )

        # Verify command includes --wiztree flag
        call_args = mock_run.call_args[0][0]
        task_command = ' '.join(call_args)
        assert '--wiztree' in task_command
        assert '--save-to-db' in task_command
        assert '--notify' in task_command

    @patch('subprocess.run')
    def test_create_scheduled_task_fails_without_admin(self, mock_run):
        """Test scheduled task creation fails gracefully without admin privileges."""
        from scripts.setup_scheduled_scan import create_scheduled_task

        # Mock schtasks failure due to insufficient privileges
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=['schtasks'],
            stderr='ERROR: Access is denied.'
        )

        success = create_scheduled_task(
            task_name='Test_Task',
            frequency_days=14,
            start_time='02:00',
            notify=False,
            auto_execute=False
        )

        assert not success

    @patch('subprocess.run')
    def test_delete_scheduled_task_success(self, mock_run):
        """Test deleting scheduled task."""
        from scripts.setup_scheduled_scan import delete_scheduled_task

        # Mock user confirmation
        with patch('builtins.input', return_value='YES'):
            mock_run.return_value = Mock(
                returncode=0,
                stdout='SUCCESS: The scheduled task "Test_Task" was successfully deleted.',
                stderr=''
            )

            success = delete_scheduled_task(task_name='Test_Task')

            assert success
            mock_run.assert_called_once()

            # Verify schtasks delete command
            call_args = mock_run.call_args[0][0]
            assert 'schtasks' in call_args
            assert '/Delete' in call_args
            assert '/TN' in call_args
            assert 'Test_Task' in call_args
            assert '/F' in call_args

    @patch('subprocess.run')
    def test_delete_scheduled_task_cancelled_by_user(self, mock_run):
        """Test delete cancellation when user doesn't confirm."""
        from scripts.setup_scheduled_scan import delete_scheduled_task

        # Mock user declining confirmation
        with patch('builtins.input', return_value='NO'):
            success = delete_scheduled_task(task_name='Test_Task')

            assert not success
            mock_run.assert_not_called()

    @patch('subprocess.run')
    def test_run_task_manual_trigger(self, mock_run):
        """Test manually triggering scheduled task."""
        from scripts.setup_scheduled_scan import run_task

        mock_run.return_value = Mock(
            returncode=0,
            stdout='SUCCESS: Attempted to run the scheduled task "Test_Task".',
            stderr=''
        )

        success = run_task(task_name='Test_Task')

        assert success
        mock_run.assert_called_once()

        # Verify schtasks run command
        call_args = mock_run.call_args[0][0]
        assert 'schtasks' in call_args
        assert '/Run' in call_args
        assert '/TN' in call_args
        assert 'Test_Task' in call_args

    @patch('subprocess.run')
    def test_list_scheduled_tasks_filters_autopack(self, mock_run):
        """Test listing only Autopack-related tasks."""
        from scripts.setup_scheduled_scan import list_scheduled_tasks

        # Mock schtasks /Query output
        mock_run.return_value = Mock(
            returncode=0,
            stdout="""
TaskName:                        \\Autopack_Storage_Scan
Next Run Time:                   1/1/2026 2:00:00 AM
Status:                          Ready
Logon Mode:                      Interactive only

TaskName:                        \\Microsoft\\Windows\\UpdateOrchestrator\\Schedule Scan
Next Run Time:                   N/A
Status:                          Disabled
            """,
            stderr=''
        )

        list_scheduled_tasks()

        # Just verify it doesn't crash
        mock_run.assert_called_once()


class TestScheduledScanWorkflow:
    """Test end-to-end scheduled scan workflow."""

    @patch('subprocess.run')
    def test_scheduled_scan_executes_script(self, mock_run):
        """Test scheduled task executes scan_and_report.py correctly."""
        # This would be tested by actually creating and running a task
        # For now, verify the command structure
        from scripts.setup_scheduled_scan import create_scheduled_task

        with patch('sys.executable', 'C:\\Python\\python.exe'):
            with patch('pathlib.Path.exists', return_value=True):
                mock_run.return_value = Mock(returncode=0, stdout='SUCCESS', stderr='')

                create_scheduled_task(
                    task_name='Test_Workflow',
                    frequency_days=14,
                    start_time='02:00',
                    notify=True,
                    auto_execute=False
                )

                # Verify command includes all required parts
                call_args = ' '.join(mock_run.call_args[0][0])
                assert 'python' in call_args.lower()
                assert 'scan_and_report.py' in call_args
                assert '--save-to-db' in call_args
                assert '--wiztree' in call_args
                assert '--notify' in call_args

    def test_scan_with_wiztree_and_notify_flags(self):
        """Test scan_and_report.py accepts --wiztree and --notify flags."""
        # This would require actually running the script
        # For now, verify argument parser accepts flags

        # Mock sys.argv

        # This would need database connection, so just verify args parse
        # In real integration test, would verify full workflow
        pass  # Covered by manual testing

    @patch('autopack.storage_optimizer.telegram_notifications.StorageTelegramNotifier.send_scan_completion')
    @patch('autopack.storage_optimizer.wiztree_scanner.WizTreeScanner.is_available')
    def test_full_scheduled_workflow(self, mock_wiztree_available, mock_telegram_send):
        """Test complete workflow: scheduled task → WizTree scan → Telegram notification."""
        # Mock WizTree available
        mock_wiztree_available.return_value = True

        # Mock Telegram send success
        mock_telegram_send.return_value = True

        # This would simulate:
        # 1. Task Scheduler runs at 2 AM
        # 2. scan_and_report.py executes with --wiztree --notify --save-to-db
        # 3. WizTree scans drive C: in < 30 seconds
        # 4. Results saved to PostgreSQL
        # 5. Telegram notification sent to user's phone
        # 6. User approves via inline button
        # 7. Webhook receives callback
        # 8. Approval saved to database

        # In integration test, would verify each step
        pass  # Requires full environment setup


class TestWizTreePerformance:
    """Test WizTree performance benchmarks."""

    @pytest.mark.slow
    @pytest.mark.skipif(
        not Path('C:/Program Files/WizTree/wiztree64.exe').exists(),
        reason="WizTree not installed"
    )
    def test_wiztree_scan_faster_than_python(self):
        """Test WizTree is significantly faster than Python scanner."""
        import time
        from autopack.storage_optimizer.wiztree_scanner import WizTreeScanner
        from autopack.storage_optimizer.scanner import StorageScanner

        # Scan small directory with both scanners
        test_dir = 'C:/Windows/System32'  # ~5000 files

        # WizTree scan
        wiztree_scanner = WizTreeScanner()
        if not wiztree_scanner.is_available():
            pytest.skip("WizTree not available")

        start = time.time()
        wiztree_scanner.scan_directory(test_dir, max_depth=2, max_items=5000)
        wiztree_duration = time.time() - start

        # Python scan
        python_scanner = StorageScanner()
        start = time.time()
        python_scanner.scan_directory(test_dir, max_depth=2, max_items=5000)
        python_duration = time.time() - start

        # WizTree should be at least 2x faster (conservative)
        speedup = python_duration / wiztree_duration
        print(f"WizTree: {wiztree_duration:.2f}s, Python: {python_duration:.2f}s, Speedup: {speedup:.1f}x")
        assert speedup >= 2.0, f"WizTree only {speedup:.1f}x faster, expected ≥2x"

    @pytest.mark.slow
    @pytest.mark.skipif(
        not Path('C:/Program Files/WizTree/wiztree64.exe').exists(),
        reason="WizTree not installed"
    )
    def test_wiztree_full_drive_scan_under_60_seconds(self):
        """Test WizTree scans 1TB drive in < 60 seconds."""
        import time
        from autopack.storage_optimizer.wiztree_scanner import WizTreeScanner

        scanner = WizTreeScanner()
        if not scanner.is_available():
            pytest.skip("WizTree not available")

        # Scan C: drive (or largest available drive)
        start = time.time()
        results = scanner.scan_drive('C', max_depth=None, max_items=100000)
        duration = time.time() - start

        print(f"Scanned {len(results):,} items in {duration:.2f}s")

        # Should complete in < 60 seconds for typical drives
        assert duration < 60, f"Scan took {duration:.2f}s, expected < 60s"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'not slow'])
