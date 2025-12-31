from core.states import State


def get_screen(state, callbacks):
    # Lazy-import screen classes to avoid import-time issues
    if state == State.IDLE:
        from ui.idle_screen import IdleScreen
        return IdleScreen(callbacks["start_listening"])

    elif state == State.LISTENING:
        from ui.listening_screen import ListeningScreen
        return ListeningScreen()

    elif state == State.PROCESSING:
        from ui.processing_screen import ProcessingScreen
        return ProcessingScreen()

    elif state == State.DISPLAYING:
        from ui.displaying_screen import DisplayingScreen
        approve = callbacks.get("approve_print") if callbacks else None
        return DisplayingScreen(approve)

    elif state == State.PRINTING:
        from ui.printing_screen import PrintingScreen
        return PrintingScreen()

    elif state == State.ERROR:
        from ui.error_screen import ErrorScreen
        return ErrorScreen(callbacks)

    else:
        raise ValueError(f"Unhandled state: {state}")