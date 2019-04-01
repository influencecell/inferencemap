# -*- coding: utf-8 -*-

# Copyright © 2019, Institut Pasteur
#   Contributor: François Laurent

# This file is part of the TRamWAy software available at
# "https://github.com/DecBayComp/TRamWAy" and is distributed under
# the terms of the CeCILL license as circulated at the following URL
# "http://www.cecill.info/licenses.en.html".

# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL license and that you accept its terms.


import multiprocessing
try:
    import queue
except ImportError:
    import Queue as queue
import time
import numpy as np
from warnings import warn
try:
    from . import abc
except SyntaxError: # Py2
    import abc_py2 as abc


class StarQueue(object):
    """
    A star queue is a multidirectional queue such that each message must be consumed
    by every processes but the sender.
    This is useful to send asynchronous updates between processes in a distributed setting.

    A `StarQueue` is instanciated first, and then `StarConn` objects are delt to
    children processes.
    The `StarConn` objects are the actual queues.
    """
    __slots__ = ('deck',)
    def __init__(self, n, variant=multiprocessing.Queue, **kwargs):
        self.deck = []
        queues = [ variant(**kwargs) for _ in range(n) ]
        others = []
        for _ in range(n):
            _queue = queues.pop()
            self.deck.append((_queue, queues+others))
            others.append(_queue)
    def deal(self):
        try:
            return StarConn(*self.deck.pop())
        except IndexError:
            raise RuntimeError('too many consumers')

class StarConn(queue.Queue):
    __slots__ = ('input', 'output')
    def __init__(self, input_queue=None, output_queues=None):
        queue.Queue.__init__(self)
        self.input = input_queue
        self.output = output_queues
    @property
    def joinable(self):
        return isinstance(self.input, multiprocessing.JoinableQueue)
    @property
    def variant(self):
        return type(self.input)
    def qsize(self):
        return sum( q.qsize() for q in self.output )
    def empty(self):
        return all( q.empty() for q in self.output )
    def full(self):
        return any( q.full()  for q in self.output)
    def put(self, obj, block=True, timeout=None):
        if timeout and 0 < timeout:
            t0 = time.time()
        _timeout = timeout
        for _queue in self.output:
            _queue.put(obj, block, _timeout)
            if timeout and 0 < timeout:
                _timeout = timeout - (time.time() - t0)
    def put_nowait(self, obj):
        for _queue in self.output:
            _queue.put_nowait(obj)
    def get(self, block=True, timeout=None):
        return self.input.get(block, timeout)
    def get_nowait(self):
        return self.input.get_nowait()
    def close(self):
        if self.output is None:
            raise RuntimeError('queue not yet `close` should not be called by the parent process')
        for _queue in self.output:
            _queue.close()
    def join_thread(self):
        if self.output is None:
            raise RuntimeError('`join_thread` should not be called by the parent process')
        for _queue in self.output:
            _queue.join_thread()
    def task_done(self):
        if self.input is None:
            raise RuntimeError('no task was received through the queue')
        try:
            self.input.task_done()
        except (SystemExit, KeyboardInterrupt):
            raise
        except:
            if self.joinable:
                raise
            else:
                raise RuntimeError('queue was not set as joinable at init')


class Worker(multiprocessing.Process):
    """ Worker that runs job steps.

    The `target` method may be implemented following the pattern below::

        class MyWorker(Worker):
            def target(self, *args, **kwargs):
                while True:
                    k, task = self.get_task()
                    status = dict()
                    try:
                        # modify `task` and `status`
                    finally:
                        self.push_update(task, status)

    The optional positional and keyword arguments come from the `args` and `kwargs` arguments
    to :meth:`Scheduler.__init__`, plus the extra keyword arguments to the latter constructor.

    """
    def __init__(self, workspace, task_queue, return_queue, update_queue,
            name=None, args=(), kwargs={}, daemon=None):
        # `daemon` is not supported in Py2; pass `daemon` only if defined
        if daemon is None:
            _kwargs = {}
        else:
            _kwargs = dict(daemon=daemon)
        multiprocessing.Process.__init__(self, name=name, args=args, kwargs=kwargs, **_kwargs)
        self.workspace = workspace
        self.tasks = task_queue
        self.update = update_queue
        self.feedback = return_queue
        self.args = args
        self.kwargs = kwargs
    def get_task(self):
        """ Listen to the scheduler and get a job step to be run.

        The job step is loaded with the worker-local copy of the synchronized workspace.

        Returns:

            int, JobStep: step/iteration number, job step object.

        """
        k, task = self.tasks.get()
        task.set_workspace(self.workspace)
        self.pull_updates()
        return k, task
    def push_update(self, update, status=None):
        """ Send a completed job step back to the scheduler and to the other workers.

        Arguments:

            update (JobStep): completed job step.

            status (any): extra information that :meth:`Scheduler.stop` will receive.

        """
        update.unset_workspace() # free memory space
        if self.update is not None:
            self.update.put(update)
        self.feedback.put((update, status))
    def pull_updates(self):
        if self.update is None:
            return
        while True:
            try:
                update = self.update.get_nowait()
            except queue.Empty:
                break
            else:
                self.workspace.update(update) # `Workspace.update` reloads the workspace into the update
    def run(self):
        self.target(*self.args, **self.kwargs)


class Scheduler(object):
    """ Scheduler that distributes job steps over a shared workspace.

    Workers are spawned and assigned job steps.
    Each worker maintains a copy of the common workspace that is synchronized
    by :meth:`Worker.push_update` calls.

    The :meth:`stop` method should be overloaded so that the distributed computation
    may complete on termination criteria.
    """
    def __init__(self, workspace, tasks, worker_count=None, iter_max=None,
            name=None, args=(), kwargs={}, daemon=None, **_kwargs):
        """
        Arguments:

            workspace (Workspace): workspace to be replicated
        """
        self.workspace = workspace
        self.task = tasks
        self.active = dict()
        self.paused = dict()
        self.k_eff = 0
        self.k_max = iter_max
        if not worker_count:
            worker_count = multiprocessing.cpu_count() - 1
        if worker_count == 1:
            self.workers = []
            raise NotImplementedError('single process')
        else:
            def _name(w):
                return '{}-{:d}'.format(name, w) if w else None
            kwargs.update(_kwargs)
            self.task_queue = multiprocessing.Queue()
            self.return_queue = multiprocessing.Queue()
            update_queue = StarQueue(worker_count)
            self.workers = [ self.worker(self.workspace,
                        self.task_queue, self.return_queue, update_queue.deal(),
                        name=_name(w), args=args, kwargs=kwargs, daemon=daemon)
                    for w in range(worker_count) ]
    def init_resource_lock(self):
        self.resource_lock = np.zeros(len(self.workspace), dtype=bool)
    @property
    def worker(self):
        return Worker
    @property
    def worker_count(self):
        return max(1, len(self.workers))
    def draw(self, k):
        return k
    def locked(self, step):
        return step.step_id in self.active or \
                np.any(self.resource_lock[step.resource_id])
    def lock(self, step):
        self.resource_lock[step.resource_id] = True
    def unlock(self, step):
        self.resource_lock[step.resource_id] = False
    @property
    def available_slots(self):
        """
        `int`: Number of available workers.
        """
        return self.worker_count - len(self.active)
    def send_task(self, k, step):
        """
        Send a job step to be assigned to a worker as soon as possible.

        Arguments:

            k (int): step/iteration number.

            step (JobStep): job step.

        """
        self.active[step.step_id] = k
        self.lock(step)
        step.unset_workspace() # free memory
        self.task_queue.put((k, step))
        self.k_eff += 1
    def get_processed_step(self):
        """
        Retrieve a processed job step and check whether stopping criteria are met.

        Calls the :meth:`stop` method.

        Returns ``False`` if a stopping criterion has been met, ``True`` otherwise.
        """
        step, status = self.return_queue.get()
        #step.set_workspace(self.workspace) # reload workspace
        self.workspace.update(step) # `update` reloads the workspace into `step`
        assert step.get_workspace() is not None
        i = step.step_id
        self.task[i] = step
        k = self.active.pop(i)
        if self.stop(k, i, status):
            return False
        self.unlock(step)
        return True
    def iter_max_reached(self):
        return self.k_max and self.k_max <= self.k_eff
    def fill_slots(self, k, postponed):
        """
        Send as many job steps as there are available workers.

        Arguments:

            k (int) : step/iteration number.

            postponed (dict): postponed job steps.

        Returns:

            int: new step/iteration number.

        """
        while 0 < self.available_slots:
            i = self.draw(k)
            if i is not None:
                task = self.task[i]
                if i in self.active or i in postponed:
                    break
                elif self.locked(task):
                    postponed[i] = k
                else:
                    self.send_task(k, task)
            k += 1
            if self.iter_max_reached():
                break
        return k
    def run(self):
        """
        Start the workers, send and get job steps back and check for stop criteria.

        Returns ``True`` on normal completion, ``False`` on interruption (SystemExit, KeyboardInterrupt).
        """
        for w in self.workers:
            w.start()
        self.init_resource_lock()
        k = 0
        postponed = dict()
        try:
            k = self.fill_slots(k, postponed)
            while not self.iter_max_reached():
                if not self.get_processed_step():
                    break
                if postponed:
                    for i in list(postponed):
                        task = self.task[i]
                        if not self.locked(task):
                            self.send_task(postponed.pop(i), task)
                            if self.available_slots == 0:
                                break
                            else:
                                assert 0 < self.available_slots
                if not postponed:
                    k = self.fill_slots(k, postponed)
            ret = True
        except (SystemExit, KeyboardInterrupt):
            ret = False
        for w in self.workers:
            try:
                w.terminate()
            except:
                pass
    def stop(self, k, i, status):
        """
        Default implementation returns ``False``.

        Arguments:

            k (int): step/interation number.

            i (int): step id.

            status (dict): status data returned by a job step.

        Returns:

            bool: ``True`` if a stopping criterion has been met, ``False`` otherwise.

        """
        return False


class Workspace(object):
    """ Parameter singleton.

    Attributes:

        data_array (array-like): working copy of the parameter vector.

    """
    __slots__ = ('data_array',)
    def __init__(self, data_array):
        self.data_array = data_array
    def __len__(self):
        return len(self.data_array)
    def update(self, step):
        step.set_workspace(self)

abc.Workspace.register(Workspace)


class JobStep(object):
    """ Job step.

    Job steps contain all the necessary data and is editable so that a completed
    job step is still a job step object to be pushed as an update.

    A job step operates on a part of the common workspace data,
    and multiple steps can operate simultaneously in the same workspace in a distributed fashion.

    A job step locks the target piece of data and operates on it.
    Related model parameters are updated in the shared workspace.

    `step_id` is not an iteration number, but an index that uniquely indentifies
    the target piece of data in the workspace.
    Multiple job steps may have the same `step_id` but they cannot run at once.

    `resource_id` is an index array that designates the units of data to be processed.
    The attribute allows to lock these items of data, which determines which steps can be
    run simultaneously.
    """
    __slots__ = ('_id', '_workspace')
    def __init__(self, _id, workspace=None):
        self._id = _id
        self._workspace = workspace
    def get_workspace(self):
        return self._workspace
    def set_workspace(self, ws):
        self._workspace = ws
    def unset_workspace(self):
        self._workspace = None
    @property
    def workspace_set(self):
        return self._workspace is not None
    @property
    def step_id(self):
        return self._id

abc.JobStep.register(JobStep)


__all__ = [ 'StarConn', 'StarQueue', 'Workspace', 'JobStep', 'Worker', 'Scheduler', 'abc' ]
