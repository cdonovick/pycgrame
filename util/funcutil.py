import functools as ft
import typing as tp
import inspect

R = tp.TypeVar('R')
def AutoPartial(n : int) -> tp.Callable[[tp.Callable[..., R]], tp.Callable[..., R]]:
    def _Partial(f : tp.Callable[..., R]) -> tp.Callable[..., R]:
        @ft.wraps(f)
        def wrapper(*args) -> tp.Callable[..., R]:
            l = len(args)
            if l < n:
                raise TypeError('Incorrect number of arguments')
            elif l > n:
                raise TypeError('Incorrect number of arguments')

            p = ft.partial(f, *args)
            arg_str = ", ".join(map(repr,args))
            suffix = '(' + arg_str + ')'
            p.__name__ = f.__name__ + suffix
            p.__qualname__ = f.__qualname__ + suffix
            return p
        return wrapper
    return _Partial



