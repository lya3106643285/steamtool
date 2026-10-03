"""Source checkout compatibility entry; installed users call Steamtool."""
from steamtool.main import main

if __name__ == "__main__":
    raise SystemExit(main())
