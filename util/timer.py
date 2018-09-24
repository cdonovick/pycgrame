import typing as tp
from . import views

T = tp.TypeVar('T')
class Timer:
    _time_func : tp.Callable[[], T]
    _times : tp.List[T]
    _start_times : tp.List[T]

    def __init__(self, time_func):
        self._time_func = time_func
        self._times = []
        self._start_times = []

    def reset(self):
        self._times = []
        self._start_times = []

    def start(self):
        t = self._time_func()
        if self.running:
            self._times.append(t - self._start_times[-1])
        self._start_times.append(t)

    def stop(self):
        if self.running: 
            self._times.append(self._time_func() - self._start_times[-1])

    @property
    def running(self) -> bool:
        return len(self._times) != len(self._start_times)

    @property
    def times(self) -> tp.Sequence[T]:
        return views.SequenceView(self._times)

    @property
    def total(self) -> T:
        return sum(self.times)


class _NullTimer(Timer):
    def __init__(self): pass
    def reset(self): pass
    def start(self): pass
    def stop(self): pass

    _start_times = tuple()
    _times = tuple()

_NullTimer.__name__ = 'NullTimer'
_inst=None 
def NullTimer():
    global _inst
    if _inst is None:
        _inst = _NullTimer()
    return _inst

