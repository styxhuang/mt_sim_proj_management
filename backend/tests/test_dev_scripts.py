import pathlib
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
START_DEV = (PROJECT_ROOT / "start-dev.sh").read_text(encoding="utf-8")


class DevScriptTests(unittest.TestCase):
    def test_start_dev_loads_bashrc_before_starting_services(self) -> None:
        self.assertIn('if [[ -f "$HOME/.bashrc" ]]', START_DEV)
        self.assertIn('set -a', START_DEV)
        self.assertIn('source "$HOME/.bashrc"', START_DEV)
        self.assertLess(
            START_DEV.index('source "$HOME/.bashrc"'),
            START_DEV.index('PORT="$BACKEND_PORT" nohup'),
        )


if __name__ == "__main__":
    unittest.main()
