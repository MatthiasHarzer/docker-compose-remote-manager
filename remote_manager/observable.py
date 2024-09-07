from typing import Callable

type Observer[T] = Callable[[T], None]
type Unsubscriber = Callable[[], None]


class Observable[T]:
    """
    Can be observed by other objects.
    """

    def __new__(cls, *args, **kwargs):
        """
        Using __new__ method instead of __init__ to avoid calling the super.__init__ method in the derived class.
        """
        c = super().__new__(cls)
        c._observers: list[T] = []  # type: ignore[attr-defined]

        return c

    def clear_observers(self) -> None:
        """
        Clears all observers.
        """
        self._observers.clear()  # type: ignore[attr-defined]

    def listen(self, observer: Observer[T]) -> Unsubscriber:
        """
        Registers a callback that will be called when the observable is notified.
        """
        self._observers.append(observer)  # type: ignore[attr-defined]

        def unsubscribe() -> None:
            self._observers.remove(observer)  # type: ignore[attr-defined]

        return unsubscribe

    def notify(self, value: T | None = None) -> None:
        """
        Calls all registered callbacks.
        """
        for observer in self._observers:  # type: ignore[attr-defined]
            observer(value)
