"""Code common to Connection and Channel objects."""
# Copyright (C) 2007-2008 Barry Pederson <bp@barryp.org>)
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
from typing import Any, Callable, Coroutine, Sequence, Union
from vine import Thenable, ensure_promise, promise
from .exceptions import AMQPNotImplementedError, RecoverableConnectionError
from .serialization import dumps, loads
from .types import ConnectionT
from .spec import method_sig_t
from .utils import coroutine

WaitMethodT = Union[method_sig_t, Sequence[method_sig_t]]

__all__ = ['ChannelBase']


class ChannelBase:
    """Superclass for Connection and Channel.

    The connection is treated as channel 0, then comes
    user-created channel objects.

    The subclasses must have a _METHOD_MAP class property, mapping
    between AMQP method signatures and Python methods.
    """

    def __init__(self, connection: ConnectionT, channel_id: int):
        self.connection = connection
        self.channel_id = channel_id
        connection.channels[channel_id] = self
        self.method_queue = []  # Higher level queue for methods
        self.auto_decode = False
        self._pending = {}
        self._callbacks = {}

        self._setup_listeners()

    def __enter__(self) -> 'ChannelBase':
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @coroutine
    def send_method(self, sig: method_sig_t,
                    format: str = None,
                    args: Sequence = None,
                    content: bytes = None,
                    wait: WaitMethodT = None,
                    callback: Callable = None,
                    returns_tuple: bool = False) -> Thenable:
        p = promise()
        conn = self.connection
        if conn is None:
            raise RecoverableConnectionError('connection already closed')
        args = dumps(format, args) if format else ''
        try:
            yield from conn.frame_writer(
                1, self.channel_id, sig, args, content)
        except StopIteration:
            raise RecoverableConnectionError('connection already closed')

        # TODO temp: callback should be after write_method ... ;)
        p()
        if callback:
            cbret = callback()
            if isinstance(cbret, Coroutine):
                yield from cbret
        if wait:
            yield from self.wait(wait, returns_tuple=returns_tuple)
        yield p

    @coroutine
    def close(self) -> None:
        """Close this Channel or Connection."""
        raise NotImplementedError('Must be overriden in subclass')

    @coroutine
    def wait(self,
             method: WaitMethodT,
             callback: Callable = None,
             timeout: float = None,
             returns_tuple: bool = False) -> Any:
        p = ensure_promise(callback)
        pending = self._pending
        prev_p = []
        if not isinstance(method, list):
            method = [method]

        for m in method:
            prev_p.append(pending.get(m))
            pending[m] = p

        try:
            while not p.ready:
                yield from self.connection.drain_events(timeout=timeout)

            if p.value:
                args, kwargs = p.value
                yield args if returns_tuple else (args and args[0])
        finally:
            for i, m in enumerate(method):
                if prev_p[i] is not None:
                    pending[m] = prev_p[i]
                else:
                    pending.pop(m, None)

    @coroutine
    def dispatch_method(self,
                        method_sig: method_sig_t,
                        payload: bytes,
                        content: bytes) -> None:
        if content and \
                self.auto_decode and \
                hasattr(content, 'content_encoding'):
            try:
                content.body = content.body.decode(content.content_encoding)
            except Exception:
                pass

        try:
            amqp_method = self._METHODS[method_sig]
        except KeyError:
            raise AMQPNotImplementedError(
                'Unknown AMQP method {0!r}'.format(method_sig))

        try:
            listeners = [self._callbacks[method_sig]]
        except KeyError:
            listeners = None
        try:
            one_shot = self._pending.pop(method_sig)
        except KeyError:
            if not listeners:
                return
        else:
            if listeners is None:
                listeners = [one_shot]
            else:
                listeners.append(one_shot)

        args = []
        if amqp_method.args:
            args, _ = loads(amqp_method.args, payload, 4)
        if amqp_method.content:
            args.append(content)

        for listener in listeners:
            lisret = listener(*args)
            if isinstance(lisret, Coroutine):
                yield from lisret

    #: Placeholder, the concrete implementations will have to
    #: supply their own versions of _METHOD_MAP
    _METHODS = {}
