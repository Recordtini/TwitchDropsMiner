from __future__ import annotations

from multiprocessing import freeze_support

if __name__ == "__main__":
    freeze_support()
    import sys
    import signal
    import asyncio
    import logging
    import argparse
    import warnings
    import traceback
    
    import truststore
    truststore.inject_into_ssl()

    from translate import _
    # We import the 'twitch' module itself, not the class directly
    import twitch
    from settings import Settings
    from version import __version__
    from exceptions import CaptchaRequired
    # These are needed for our monkey-patch
    from headless import HeadlessGUIManager
    from gui import GUIManager
    from utils import lock_file
    from constants import LOGGING_LEVELS, SELF_PATH, FILE_FORMATTER, LOG_PATH, LOCK_PATH

    warnings.simplefilter("default", ResourceWarning)

    class ParsedArgs(argparse.Namespace):
        _verbose: int; log: bool; tray: bool; dump: bool; headless: bool
        _debug_ws: bool; _debug_gql: bool
        @property
        def logging_level(self) -> int: return LOGGING_LEVELS.get(min(self._verbose, 4), logging.DEBUG)
        @property
        def debug_ws(self) -> int: return logging.DEBUG if self._debug_ws else logging.NOTSET
        @property
        def debug_gql(self) -> int: return logging.DEBUG if self._debug_gql else logging.NOTSET

    parser = argparse.ArgumentParser(SELF_PATH.name)
    parser.add_argument("--version", action="version", version=f"v{__version__}")
    parser.add_argument("-v", dest="_verbose", action="count", default=0)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--dump", action="store_true")
    parser.add_argument("--tray", action="store_true")
    parser.add_argument("--debug-ws", dest="_debug_ws", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--debug-gql", dest="_debug_gql", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(namespace=ParsedArgs())
    
    try:
        settings = Settings(args)
    except Exception:
        print(f"Error loading settings:\n{traceback.format_exc()}"); sys.exit(4)

    async def main():
        try:
            _.set_language(settings.language)
        except (ValueError, FileNotFoundError):
            pass

        if settings.logging_level > logging.DEBUG:
            logging.getLogger().addHandler(logging.NullHandler())
        
        logger = logging.getLogger("TwitchDrops")
        logger.setLevel(settings.logging_level)
        
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
        logger.addHandler(console_handler)

        if settings.log:
            handler = logging.FileHandler(LOG_PATH)
            handler.setFormatter(FILE_FORMATTER)
            logger.addHandler(handler)
        
        logging.getLogger("TwitchDrops.gql").setLevel(settings.debug_gql)
        logging.getLogger("TwitchDrops.websocket").setLevel(settings.debug_ws)

        # --- THIS IS THE CORRECT MONKEY-PATCH ---
        if args.headless:
            # We overwrite the GUIManager class inside the 'twitch' module
            # *before* an instance of the Twitch class is created.
            twitch.GUIManager = HeadlessGUIManager
        
        # We create the client using twitch.Twitch, WITHOUT the headless argument.
        client = twitch.Twitch(settings)
        # --- END OF CORRECT LOGIC ---

        loop = asyncio.get_running_loop()
        if sys.platform == "linux":
            for s in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(s, client.close)
        
        exit_status = 0
        try:
            await client.run()
        except Exception:
            exit_status = 1
            client.print("Fatal error encountered:\n")
            client.print(traceback.format_exc())
        finally:
            client.print("Exiting...")
            await client.shutdown()
        
        if not args.headless and hasattr(client.gui, 'wait_until_closed'):
            await client.gui.wait_until_closed()
            client.gui.stop()
        
        sys.exit(exit_status)

    try:
        success, file = lock_file(LOCK_PATH)
        if not success: sys.exit(3)
        asyncio.run(main())
    finally:
        file.close()