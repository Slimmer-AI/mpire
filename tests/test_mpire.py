import ctypes
import types
import unittest
from itertools import product, repeat
from multiprocessing import Barrier, managers, Value
from unittest.mock import patch

import numpy as np

from mpire import cpu_count, WorkerPool


def square(idx, x):
    return idx, x * x


def square_numpy(x):
    return x * x


class MapTest(unittest.TestCase):

    def setUp(self):
        # Create some test data. Note that the regular map reads the inputs as a list of single tuples (one argument),
        # whereas parallel.map sees it as a list of argument lists. Therefore we give the regular map a lambda function
        # which mimics the parallel.map behavior.
        self.test_data = list(enumerate([1, 2, 3, 5, 6, 9, 37, 42, 1337, 0, 3, 5, 0]))
        self.test_desired_output = list(map(lambda _args: square(*_args), self.test_data))
        self.test_data_len = len(self.test_data)

        # Numpy test data
        self.test_data_numpy = np.random.rand(100, 2)
        self.test_desired_output_numpy = square_numpy(self.test_data_numpy)
        self.test_data_len_numpy = len(self.test_data_numpy)

    def test_all_maps(self):
        """
        Tests the map related functions
        """

        def get_generator(iterable):
            yield from iterable

        # Test results for different number of jobs to run in parallel and the maximum number of active tasks in the
        # queue
        for n_jobs, n_tasks_max_active, worker_lifespan, chunk_size, n_splits in \
                product([1, 2, None], [None, 2], [None, 2], [None, 3], [None, 3]):

            with WorkerPool(n_jobs=n_jobs) as pool:

                for map_func, sort, result_type in ((pool.map, False, list), (pool.map_unordered, True, list),
                                                    (pool.imap, False, types.GeneratorType),
                                                    (pool.imap_unordered, True, types.GeneratorType)):

                    with self.subTest(map_func=map_func, input='list', n_jobs=n_jobs,
                                      n_tasks_max_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                      chunk_size=chunk_size, n_splits=n_splits):

                        # Test if parallel map results in the same as ordinary map function. Should work both for
                        # generators and iterators. Also check if an empty list works as desired.
                        results_list = map_func(square, self.test_data, max_tasks_active=n_tasks_max_active,
                                                worker_lifespan=worker_lifespan)
                        self.assertTrue(isinstance(results_list, result_type))
                        self.assertEqual(self.test_desired_output,
                                         sorted(results_list, key=lambda tup: tup[0]) if sort else list(results_list))

                    with self.subTest(map_func=map_func, input='generator', n_jobs=n_jobs,
                                      n_tasks_max_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                      chunk_size=chunk_size, n_splits=n_splits):

                        results_list = map_func(square, get_generator(self.test_data), iterable_len=self.test_data_len,
                                                max_tasks_active=n_tasks_max_active, worker_lifespan=worker_lifespan)
                        self.assertTrue(isinstance(results_list, result_type))
                        self.assertEqual(self.test_desired_output,
                                         sorted(results_list, key=lambda tup: tup[0]) if sort else list(results_list))

                    with self.subTest(map_func=map_func, input='empty list', n_jobs=n_jobs,
                                      n_tasks_max_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                      chunk_size=chunk_size, n_splits=n_splits):

                        results_list = map_func(square, [], max_tasks_active=n_tasks_max_active,
                                                worker_lifespan=worker_lifespan)
                        self.assertTrue(isinstance(results_list, result_type))
                        self.assertEqual([], list(results_list))

    def test_numpy_input(self):
        """
        Test map with numpy input
        """
        for n_jobs, n_tasks_max_active, worker_lifespan, chunk_size, n_splits in \
                product([1, 2, None], [None, 2], [None, 2], [None, 3], [None, 3]):

            with WorkerPool(n_jobs=n_jobs) as pool:

                # Test numpy input. map should concatenate chunks of numpy output to a single output array if we
                # instruct it to
                with self.subTest(concatenate_numpy_output=True, map_function='map', n_jobs=n_jobs,
                                  n_tasks_max_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                  chunk_size=chunk_size, n_splits=n_splits):
                    results = pool.map(square_numpy, self.test_data_numpy, max_tasks_active=n_tasks_max_active,
                                       worker_lifespan=worker_lifespan, concatenate_numpy_output=True)
                    self.assertTrue(isinstance(results, np.ndarray))
                    np.testing.assert_array_equal(results, self.test_desired_output_numpy)

                # If we disable it we should get back chunks of the original array
                with self.subTest(concatenate_numpy_output=False, map_function='map', n_jobs=n_jobs,
                                  n_tasks_max_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                  chunk_size=chunk_size, n_splits=n_splits):
                    results = pool.map(square_numpy, self.test_data_numpy, max_tasks_active=n_tasks_max_active,
                                       worker_lifespan=worker_lifespan, concatenate_numpy_output=False)
                    self.assertTrue(isinstance(results, list))
                    np.testing.assert_array_equal(np.concatenate(results), self.test_desired_output_numpy)

                # Numpy concatenation doesn't exist for the other functions
                with self.subTest(map_function='imap', n_jobs=n_jobs, n_tasks_max_active=n_tasks_max_active,
                                  worker_lifespan=worker_lifespan, chunk_size=chunk_size, n_splits=n_splits):
                    results = pool.imap(square_numpy, self.test_data_numpy, max_tasks_active=n_tasks_max_active,
                                        worker_lifespan=worker_lifespan)
                    self.assertTrue(isinstance(results, types.GeneratorType))
                    np.testing.assert_array_equal(np.concatenate(list(results)), self.test_desired_output_numpy)

                # map_unordered and imap_unordered cannot be checked for correctness as we don't know the order of the
                # returned results, except when n_jobs=1. In the other cases we could, however, check if all the values
                # (numpy rows) that are returned are present (albeit being in a different order)
                for map_func, result_type in ((pool.map_unordered, list), (pool.imap_unordered, types.GeneratorType)):

                    with self.subTest(map_function=map_func, n_jobs=n_jobs, n_tasks_max_active=n_tasks_max_active,
                                      worker_lifespan=worker_lifespan, chunk_size=chunk_size, n_splits=n_splits):

                        results = map_func(square_numpy, self.test_data_numpy, max_tasks_active=n_tasks_max_active,
                                           worker_lifespan=worker_lifespan)
                        self.assertTrue(isinstance(results, result_type))
                        concattenated_results = np.concatenate(list(results))
                        if n_jobs == 1:
                            np.testing.assert_array_equal(concattenated_results, self.test_desired_output_numpy)
                        else:
                            # We sort the expected and actual results using lexsort, which sorts using a sequence of
                            # keys. We transpose the array to sort on columns instead of rows.
                            np.testing.assert_array_equal(
                                concattenated_results[np.lexsort(concattenated_results.T)],
                                self.test_desired_output_numpy[np.lexsort(self.test_desired_output_numpy.T)]
                            )

    def test_dictionary_input(self):
        """
        Test map with dictionary input
        """
        def subtract(x, y):
            return x - y

        with WorkerPool(n_jobs=1) as pool:

            # Should work
            with self.subTest('correct input'):
                results_list = pool.map(subtract, [{'x': 5, 'y': 2}, {'y': 5, 'x': 2}])
                self.assertEqual(results_list, [3, -3])

            # Should throw
            with self.subTest("missing 'y', unknown parameter 'z'"), self.assertRaises(TypeError):
                pool.map(subtract, [{'x': 5, 'z': 2}])

            # Should throw
            with self.subTest("unknown parameter 'z'"), self.assertRaises(TypeError):
                pool.map(subtract, [{'x': 5, 'y': 2, 'z': 2}])

    def test_faulty_parameters(self):
        """
        Should raise when wrong parameter values are used
        """
        with WorkerPool(n_jobs=4) as pool:

            # Zero (or a negative number of) active tasks/lifespan should result in a value error
            for n, map_function in product([-3, -1, 0, 3.14],
                                           [pool.map, pool.map_unordered, pool.imap, pool.imap_unordered]):
                # max_tasks_active
                with self.subTest(max_tasks_active=n, map_function=map_function), \
                     self.assertRaises(ValueError if isinstance(n, int) else TypeError):
                    list(map_function(square, self.test_data, max_tasks_active=n))

                # worker_lifespan
                with self.subTest(worker_lifespan=n, map_function=map_function), \
                     self.assertRaises(ValueError if isinstance(n, int) else TypeError):
                    list(map_function(square, self.test_data, worker_lifespan=n))

            # chunk_size should be an integer or None
            with self.subTest(chunk_size='3'), self.assertRaises(TypeError):
                for _ in pool.imap(square, self.test_data, chunk_size='3'):
                    pass

            # chunk_size should be a positive integer
            with self.subTest(chunk_size=-5), self.assertRaises(ValueError):
                for _ in pool.imap(square, self.test_data, chunk_size=-5):
                    pass

            # n_splits should be an integer or None
            with self.subTest(n_splits='3'), self.assertRaises(TypeError):
                for _ in pool.imap(square, self.test_data, n_splits='3'):
                    pass

            # n_splits should be a positive integer
            with self.subTest(n_splits=-5), self.assertRaises(ValueError):
                for _ in pool.imap(square, self.test_data, n_splits=-5):
                    pass


class WorkerIDTest(unittest.TestCase):

    def test_by_config_function(self):
        """
        Test setting passing on the worker ID using the pass_on_worker_id function
        """
        for n_jobs, pass_worker_id in product([1, 2, 4], [True, False]):

            with self.subTest(n_jobs=n_jobs, pass_worker_id=pass_worker_id, config_type='function'), \
                 WorkerPool(n_jobs=n_jobs) as pool:

                pool.pass_on_worker_id(pass_worker_id)

                # Tests should fail when number of arguments in function is incorrect, worker ID is not within range,
                # or when the shared objects are not equal to the given arguments
                f = self._f1 if pass_worker_id else self._f2
                pool.map(f, ((n_jobs,) for _ in range(10)), iterable_len=10)

    def test_by_constructor(self):
        """
        Test setting passing on the worker ID in the constructor
        """
        for n_jobs, pass_worker_id in product([1, 2, 4], [True, False]):

            with self.subTest(n_jobs=n_jobs, pass_worker_id=pass_worker_id, config_type='constructor'), \
                 WorkerPool(n_jobs=n_jobs, pass_worker_id=pass_worker_id) as pool:

                # Tests should fail when number of arguments in function is incorrect, worker ID is not within range,
                # or when the shared objects are not equal to the given arguments
                f = self._f1 if pass_worker_id else self._f2
                pool.map(f, ((n_jobs,) for _ in range(10)), iterable_len=10)

    def _f1(self, _wid, _n_jobs):
        """
        Function with worker ID
        """
        self.assertIsInstance(_wid, int)
        self.assertGreaterEqual(_wid, 0)
        self.assertLessEqual(_wid, _n_jobs)

    def _f2(self, _n_jobs):
        """
        Function without worker ID (simply tests if WorkerPool correctly handles pass_worker_id=False)
        """
        pass


class SharedObjectsTest(unittest.TestCase):

    def test_by_config_function(self):
        """
        Tests passing shared objects using the set_shared_objects function
        """
        for n_jobs, shared_objects in product([1, 2, 4], [None, (37, 42), ({'1', '2', '3'})]):

            with self.subTest(n_jobs=n_jobs, shared_objects=shared_objects, config_type='function'), \
                 WorkerPool(n_jobs=n_jobs) as pool:

                # Configure pool
                pool.set_shared_objects(shared_objects)

                # Tests should fail when number of arguments in function is incorrect, worker ID is not within range,
                # or when the shared objects are not equal to the given arguments
                f = self._f1 if shared_objects else self._f2
                pool.map(f, ((shared_objects, n_jobs) for _ in range(10)), iterable_len=10)

    def test_by_constructor(self):
        """
        Tests passing shared objects in the constructor
        """
        for n_jobs, shared_objects in product([1, 2, 4], [None, (37, 42), ({'1', '2', '3'})]):

            # Pass on arguments using the constructor instead
            with self.subTest(n_jobs=n_jobs, shared_objects=shared_objects, config_type='constructor'), \
                 WorkerPool(n_jobs=n_jobs, shared_objects=shared_objects) as pool:

                # Tests should fail when number of arguments in function is incorrect, worker ID is not within range,
                # or when the shared objects are not equal to the given arguments
                f = self._f1 if shared_objects else self._f2
                pool.map(f, ((shared_objects, n_jobs) for _ in range(10)), iterable_len=10)

    def _f1(self, _sobjects, _args, _n_jobs):
        """
        Function with shared objects
        """
        self.assertEqual(_sobjects, _args, _n_jobs)

    def _f2(self, _args, _n_jobs):
        """
        Function without shared objects (simply tests if WorkerPool correctly handles shared_objects=None)
        """
        pass


class WorkerStateTest(unittest.TestCase):

    def test_by_config_function(self):
        """
        Tests setting worker state using the set_use_worker_state function
        """
        for n_jobs, use_worker_state, n_tasks in product([1, 2, 4], [False, True], [0, 1, 3, 150]):

            with self.subTest(n_jobs=n_jobs, use_worker_state=use_worker_state, n_tasks=n_tasks),\
                 WorkerPool(n_jobs=n_jobs, pass_worker_id=True) as pool:

                pool.set_use_worker_state(use_worker_state)

                # When use_worker_state is set, the final (worker_id, n_args) of each worker should add up to the
                # number of given tasks
                f = self._f1 if use_worker_state else self._f2
                results = pool.map(f, range(n_tasks), chunk_size=2)
                if use_worker_state:
                    n_processed_per_worker = [0] * n_jobs
                    for wid, n_processed in results:
                        n_processed_per_worker[wid] = n_processed
                    self.assertEqual(sum(n_processed_per_worker), n_tasks)

    def test_by_constructor(self):
        """
        Tests setting worker state in the constructor
        """
        for n_jobs, use_worker_state, n_tasks in product([1, 2, 4], [False, True], [0, 1, 3, 150]):

            with self.subTest(n_jobs=n_jobs, use_worker_state=use_worker_state, n_tasks=n_tasks), \
                 WorkerPool(n_jobs=n_jobs, pass_worker_id=True, use_worker_state=use_worker_state) as pool:

                # When use_worker_state is set, the final (worker_id, n_args) of each worker should add up to the
                # number of given tasks
                f = self._f1 if use_worker_state else self._f2
                results = pool.map(f, range(n_tasks), chunk_size=2)
                if use_worker_state:
                    n_processed_per_worker = [0] * n_jobs
                    for wid, n_processed in results:
                        n_processed_per_worker[wid] = n_processed
                    self.assertEqual(sum(n_processed_per_worker), n_tasks)

    def _f1(self, _wid, _wstate, _arg):
        """
        Function with worker ID and worker state
        """
        self.assertTrue(isinstance(_wstate, dict))

        # Worker id should always be the same
        _wstate.setdefault('worker_id', set()).add(_wid)
        self.assertEqual(_wstate['worker_id'], {_wid})

        # Should contain previous args
        _wstate.setdefault('args', []).append(_arg)
        return _wid, len(_wstate['args'])

    def _f2(self, _wid, _):
        """
        Function with worker ID (simply tests if WorkerPool correctly handles use_worker_state=False)
        """
        pass


class InitFuncTest(unittest.TestCase):

    def setUp(self) -> None:
        self.test_data = range(10)
        self.test_desired_output = [42, 43, 44, 45, 46, 47, 48, 49, 50, 51]

    def test_no_init_func(self):
        """
        If the init func is not provided, then `worker_state['test']` should fail
        """
        with self.assertRaises(KeyError), WorkerPool(n_jobs=4, shared_objects=(None,), use_worker_state=True) as pool:
            pool.map(self._f, range(10), worker_init=None)

    def test_init_func(self):
        """
        Test if init func is called. If it is, then `worker_state['test']` should be available. Due to the barrier we
        know for sure that the init func should be called as many times as there are workers
        """
        for n_jobs in [1, 2, 4]:
            shared_objects = Barrier(n_jobs), Value('i', 0)
            with self.subTest(n_jobs=n_jobs), WorkerPool(n_jobs=n_jobs, shared_objects=shared_objects,
                                                         use_worker_state=True) as pool:
                results = pool.map(self._f, self.test_data, worker_init=self._init, chunk_size=1)
                self.assertListEqual(results, self.test_desired_output)
                self.assertEqual(shared_objects[1].value, n_jobs)

    def test_worker_lifespan(self):
        """
        When workers have a limited lifespan they are spawned multiple times. Each time a worker starts it should call
        the init function. Due to the chunk size we know for sure that the init func should be called at least once for
        each task. However, when all tasks have been processed the workers are terminated and we don't know exactly how
        many workers restarted. We only know for sure that the init func should be called between 10 and 10 + n_jobs
        times
        """
        for n_jobs in [1, 2, 4]:
            shared_objects = Barrier(n_jobs), Value('i', 0)
            with self.subTest(n_jobs=n_jobs), WorkerPool(n_jobs=n_jobs, shared_objects=shared_objects,
                                                         use_worker_state=True) as pool:
                results = pool.map(self._f, self.test_data, worker_init=self._init, chunk_size=1, worker_lifespan=1)
                self.assertListEqual(results, self.test_desired_output)
                self.assertGreaterEqual(shared_objects[1].value, 10)
                self.assertLessEqual(shared_objects[1].value, 10 + n_jobs)

    def test_error(self):
        """
        When an exception occurs in the init function it should properly shut down
        """
        with self.assertRaises(ValueError), WorkerPool(n_jobs=4, shared_objects=(None,), use_worker_state=True) as pool:
            pool.map(self._f, self.test_data, worker_init=self._init_error)

    @staticmethod
    def _init(shared_objects, worker_state):
        barrier, call_count = shared_objects

        # Only wait for the other workers the first time around (it will hang when worker_lifespan=1, otherwise)
        if call_count.value == 0:
            barrier.wait()

        with call_count.get_lock():
            call_count.value += 1
        worker_state['test'] = 42

    @staticmethod
    def _init_error(*_):
        raise ValueError(":(")

    @staticmethod
    def _f(_, worker_state, x):
        return worker_state['test'] + x


class ExitFuncTest(unittest.TestCase):

    def setUp(self) -> None:
        self.test_data = range(10)
        self.test_desired_output = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

    def test_no_exit_func(self):
        """
        If the exit func is not provided, then exit results shouldn't be available
        """
        shared_objects = Barrier(4), Value('i', 0)
        with WorkerPool(n_jobs=4, shared_objects=shared_objects, use_worker_state=True) as pool:
            results = pool.map(self._f1, range(10), worker_init=self._init, worker_exit=None)
            self.assertListEqual(results, self.test_desired_output)
            self.assertListEqual(pool.get_exit_results(), [])

    def test_exit_func(self):
        """
        Test if exit func is called. If it is, then exit results should be available. It should have as many elements
        as the number of jobs and should have the right content.
        """
        for n_jobs in [1, 2, 4]:
            shared_objects = Barrier(n_jobs), Value('i', 0)
            with self.subTest(n_jobs=n_jobs), WorkerPool(n_jobs=n_jobs, shared_objects=shared_objects,
                                                         use_worker_state=True) as pool:
                results = pool.map(self._f1, self.test_data, worker_init=self._init, worker_exit=self._exit)
                self.assertListEqual(results, self.test_desired_output)
                self.assertEqual(shared_objects[1].value, n_jobs)
                self.assertEqual(len(pool.get_exit_results()), n_jobs)
                self.assertEqual(sum(pool.get_exit_results()), sum(range(10)))

    def test_worker_lifespan(self):
        """
        When workers have a limited lifespan they are spawned multiple times. Each time a worker exits it should call
        the exit function. Due to the chunk size we know for sure that the exit func should be called at least once for
        each task. However, when all tasks have been processed the workers are terminated and we don't know exactly how
        many workers restarted. We only know for sure that the exit func should be called between 10 and 10 + n_jobs
        times
        """
        for n_jobs in [1, 2, 4]:
            shared_objects = Barrier(n_jobs), Value('i', 0)
            with self.subTest(n_jobs=n_jobs), WorkerPool(n_jobs=n_jobs, shared_objects=shared_objects,
                                                         use_worker_state=True) as pool:
                results = pool.map(self._f1, self.test_data, worker_init=self._init, worker_exit=self._exit, chunk_size=1,
                                   worker_lifespan=1)
                self.assertListEqual(results, self.test_desired_output)
                self.assertGreaterEqual(shared_objects[1].value, 10)
                self.assertLessEqual(shared_objects[1].value, 10 + n_jobs)
                self.assertEqual(len(pool.get_exit_results()), shared_objects[1].value)
                self.assertEqual(sum(pool.get_exit_results()), sum(range(10)))

    def test_exit_func_big_payload(self):
        """
        Multiprocessing Pipes have a maximum buffer size (depending on the system it can be anywhere between 16-1024kb).
        Results from the pipe need to be received from the other end, before the workers are joined. Otherwise the
        process can hang indefinitely. Because exit results are fetched in a different way as regular results, we test
        that here. We send a payload of 10_000kb.
        """
        for n_jobs, worker_lifespan in product([1, 2, 4], [None, 2]):
            with self.subTest(n_jobs=n_jobs, worker_lifespan=worker_lifespan), WorkerPool(n_jobs=n_jobs) as pool:
                results = pool.map(self._f2, self.test_data, worker_exit=self._exit_big_payloud, chunk_size=1,
                                   worker_lifespan=worker_lifespan)
                self.assertListEqual(results, self.test_desired_output)
                self.assertTrue(bool(pool.get_exit_results()))
                for exit_result in pool.get_exit_results():
                    self.assertEqual(len(exit_result), 10_000 * 1024)

    def test_error(self):
        """
        When an exception occurs in the exit function it should properly shut down
        """
        for worker_lifespan in [None, 2]:
            print("worker_lifespan=", worker_lifespan)
            with self.subTest(worker_lifespan=worker_lifespan), self.assertRaises(ValueError), \
                    WorkerPool(n_jobs=4) as pool:
                pool.map(self._f2, range(10), worker_lifespan=worker_lifespan, worker_exit=self._exit_error)

    @staticmethod
    def _init(shared_objects, worker_state):
        barrier, call_count = shared_objects

        # Only wait for the other workers the first time around (it will hang when worker_lifespan=1, otherwise)
        if call_count.value == 0:
            barrier.wait()

        worker_state['count'] = 0

    @staticmethod
    def _f1(_, worker_state, x):
        worker_state['count'] += x
        return x

    @staticmethod
    def _f2(x):
        return x

    @staticmethod
    def _exit(shared_objects, worker_state):
        _, call_count = shared_objects
        with call_count.get_lock():
            call_count.value += 1
        return worker_state['count']

    @staticmethod
    def _exit_big_payloud():
        return np.random.bytes(10_000 * 1024)

    @staticmethod
    def _exit_error():
        raise ValueError(":'(")


class DaemonTest(unittest.TestCase):

    def setUp(self):
        # Create some test data. Note that the regular map reads the inputs as a list of single tuples (one argument),
        # whereas parallel.map sees it as a list of argument lists. Therefore we give the regular map a lambda function
        # which mimics the parallel.map behavior.
        self.test_data = list(enumerate([1, 2, 3, 5, 6, 9, 37, 42, 1337, 0, 3, 5, 0]))
        self.test_desired_output = list(map(lambda _args: square(*_args), self.test_data))

    def test_non_deamon_nested_workerpool(self):
        """
        Tests nested WorkerPools when daemon==False, which should work
        """
        with WorkerPool(n_jobs=4, daemon=False) as pool:
            # Obtain results using nested WorkerPools
            results = pool.map(self._square_daemon, ((X,) for X in repeat(self.test_data, 4)), chunk_size=1)

            # Each of the results should match
            for results_list in results:
                self.assertTrue(isinstance(results_list, list))
                self.assertEqual(self.test_desired_output, results_list)

    def test_deamon_nested_workerpool(self):
        """
        Tests nested WorkerPools when daemon==True, which should not work
        """
        with self.assertRaises(AssertionError), WorkerPool(n_jobs=4, daemon=True) as pool:
            pool.map(self._square_daemon, ((X,) for X in repeat(self.test_data, 4)), chunk_size=1)

    @staticmethod
    def _square_daemon(X):
        with WorkerPool(n_jobs=4) as pool:
            return pool.map(square, X, chunk_size=1)


class CPUPinningTest(unittest.TestCase):

    def setUp(self):
        # Create some test data. Note that the regular map reads the inputs as a list of single tuples (one argument),
        # whereas parallel.map sees it as a list of argument lists. Therefore we give the regular map a lambda function
        # which mimics the parallel.map behavior.
        self.test_data = list(enumerate([1, 2, 3, 5, 6, 9, 37, 42, 1337, 0, 3, 5, 0]))
        self.test_desired_output = list(map(lambda _args: square(*_args), self.test_data))

    def test_valid_input(self):
        """
        Test that when parameters are valid, nothing breaks. We don't actually check if CPU pinning is happening
        """
        for n_jobs, cpu_ids, expected_mask in [(None, [0], [[0]] * cpu_count()),
                                               (None, [[0, 3]], [[0, 3]] * cpu_count()),
                                               (1, [0], [[0]]),
                                               (1, [[0, 3]], [[0, 3]]),
                                               (2, [0], [[0], [0]]),
                                               (2, [0, 1], [[0], [1]]),
                                               (2, [[0, 3]], [[0, 3], [0, 3]]),
                                               (2, [[0, 1], [0, 1]], [[0, 1], [0, 1]]),
                                               (4, [0], [[0], [0], [0], [0]]),
                                               (4, [0, 1, 2, 3], [[0], [1], [2], [3]]),
                                               (4, [[0, 3]], [[0, 3], [0, 3], [0, 3], [0, 3]])]:
            # The test has been designed for a system with at least 4 cores. We'll skip those test cases where the CPU
            # IDs exceed the number of CPUs.
            if cpu_ids is not None and np.array(cpu_ids).max() >= cpu_count():
                continue

            else:
                with self.subTest(n_jobs=n_jobs, cpu_ids=cpu_ids), patch('os.sched_setaffinity') as p, \
                        WorkerPool(n_jobs=n_jobs, cpu_ids=cpu_ids) as pool:

                    # Verify results
                    results_list = pool.map(square, self.test_data)
                    self.assertTrue(isinstance(results_list, list))
                    self.assertEqual(self.test_desired_output, results_list)

                    # Verify that when CPU pinning is used, it is called as many times as there are jobs and is
                    # called for each worker process ID
                    if cpu_ids is None:
                        self.assertEqual(p.call_args_list, [])
                    else:
                        self.assertEqual(p.call_count, pool.n_jobs)
                        mask = [call[0][1] for call in p.call_args_list]
                        self.assertListEqual(mask, expected_mask)

    def test_invalid_input(self):
        """
        Test that when parameters are invalid, an error is raised
        """
        for n_jobs, cpu_ids in product([None, 1, 2, 4], [[0, 1], [0, 1, 2, 3], [[0, 1], [0, 1]]]):
            if len(cpu_ids) != (n_jobs or cpu_count()):
                with self.subTest(n_jobs=n_jobs, cpu_ids=cpu_ids), self.assertRaises(ValueError):
                    WorkerPool(n_jobs=n_jobs, cpu_ids=cpu_ids)

        # Should raise when CPU IDs are out of scope
        with self.assertRaises(ValueError):
            WorkerPool(n_jobs=1, cpu_ids=[-1])
        with self.assertRaises(ValueError):
            WorkerPool(n_jobs=1, cpu_ids=[cpu_count()])


class ProgressBarTest(unittest.TestCase):

    """
    Print statements in these tests are intentional as it will print multiple progress bars
    """

    def setUp(self):
        # Create some test data. Note that the regular map reads the inputs as a list of single tuples (one argument),
        # whereas parallel.map sees it as a list of argument lists. Therefore we give the regular map a lambda function
        # which mimics the parallel.map behavior.
        self.test_data = list(enumerate([1, 2, 3, 5, 6, 9, 37, 42, 1337, 0, 3, 5, 0]))
        self.test_desired_output = list(map(lambda _args: square(*_args), self.test_data))

        # Numpy test data
        self.test_data_numpy = np.random.rand(100, 2)
        self.test_desired_output_numpy = square_numpy(self.test_data_numpy)
        self.test_data_len_numpy = len(self.test_data_numpy)

    def test_valid_progress_bars_regular_input(self):
        """
        Valid progress bars are either False/True
        """
        print()
        for n_jobs, progress_bar in product([None, 1, 2], [True, False]):

            with self.subTest(n_jobs=n_jobs), WorkerPool(n_jobs=n_jobs) as pool:
                results_list = pool.map(square, self.test_data, progress_bar=progress_bar)
                self.assertTrue(isinstance(results_list, list))
                self.assertEqual(self.test_desired_output, results_list)

    def test_valid_progress_bars_numpy_input(self):
        """
        Test with numpy, as that will change the number of tasks
        """
        print()
        for n_jobs, progress_bar in product([None, 1, 2], [True, False]):

            # Should work just fine
            with self.subTest(n_jobs=n_jobs, progress_bar=progress_bar), WorkerPool(n_jobs=n_jobs) as pool:
                results = pool.map(square_numpy, self.test_data_numpy, progress_bar=progress_bar)
                self.assertTrue(isinstance(results, np.ndarray))
                np.testing.assert_array_equal(results, self.test_desired_output_numpy)

    def test_no_input_data(self):
        """
        Test with empty iterable (this failed before)
        """
        print()
        with WorkerPool() as pool:
            self.assertListEqual(pool.map(square, [], progress_bar=True), [])

    def test_invalid_progress_bar_position(self):
        """
        Test different values of progress_bar_position, which should be positive integer >= 0
        """
        for progress_bar_position, error in [(-1, ValueError), ('numero uno', TypeError)]:
            with self.subTest(input='regular input', progress_bar_position=progress_bar_position), \
                    self.assertRaises(error), WorkerPool(n_jobs=1) as pool:
                pool.map(square, self.test_data, progress_bar=True, progress_bar_position=progress_bar_position)

            with self.subTest(input='numpy input', progress_bar_position=progress_bar_position), \
                    self.assertRaises(error), WorkerPool(n_jobs=1) as pool:
                pool.map(square_numpy, self.test_data_numpy, progress_bar=True,
                         progress_bar_position=progress_bar_position)


class StartMethodTest(unittest.TestCase):

    def setUp(self):
        # Create some test data. Note that the regular map reads the inputs as a list of single tuples (one argument),
        # whereas parallel.map sees it as a list of argument lists. Therefore we give the regular map a lambda function
        # which mimics the parallel.map behavior.
        self.test_data = list(enumerate([1, 2, 3, 5, 6, 9, 37, 42, 1337, 0, 3, 5, 0]))
        self.test_desired_output = list(map(lambda _args: square(*_args), self.test_data))

    def test_start_method(self):
        """
        Test different start methods. All should work just fine
        """
        for n_jobs, start_method in product([1, 3], ['fork', 'forkserver', 'spawn', 'threading']):
            with self.subTest(n_jobs=n_jobs, start_method=start_method), \
                 WorkerPool(n_jobs, start_method=start_method) as pool:
                self.assertListEqual(pool.map(square, self.test_data), self.test_desired_output)


class KeepAliveTest(unittest.TestCase):

    """
    In these tests we make use of a barrier. This barrier ensures that we increase the counter for each worker. If it
    wasn't there there's a chance that the first, say 3, workers already performed all the available tasks, while the
    4th worker was still spinning up. In that case the poison pill would be inserted before the fourth worker could even
    start a task and therefore couldn't increase the counter value.
    """

    def setUp(self):
        # Create some test data
        self.test_data = [1, 2, 3, 5, 6, 9, 37, 42, 1337, 0, 3, 5, 0]
        self.test_desired_output_f1 = [x * 2 for x in self.test_data]
        self.test_desired_output_f2 = [x * 3 for x in self.test_data]

    def test_dont_keep_alive(self):
        """
        When keep_alive is set to False it should restart workers between map calls. This means the counter is updated
        each time as well.
        """
        for n_jobs in [1, 2, 4]:
            barrier = Barrier(n_jobs)
            counter = Value('i', 0)
            shared = barrier, counter
            with self.subTest(n_jobs=n_jobs), \
                    WorkerPool(n_jobs=n_jobs, shared_objects=shared, use_worker_state=True, keep_alive=False) as pool:

                self.assertListEqual(pool.map(self._f1, self.test_data), self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs)
                barrier.reset()

                self.assertListEqual(pool.map(self._f1, self.test_data), self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs * 2)
                barrier.reset()

                self.assertListEqual(pool.map(self._f1, self.test_data), self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs * 3)
                barrier.reset()

                self.assertListEqual(pool.map(self._f1, self.test_data), self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs * 4)

    def test_keep_alive(self):
        """
        When keep_alive is set to True it should reuse existing workers between map calls. This means the counter is
        only updated the first time.
        """
        for n_jobs in [1, 2, 4]:
            barrier = Barrier(n_jobs)
            counter = Value('i', 0)
            shared = barrier, counter
            with self.subTest(n_jobs=n_jobs), \
                    WorkerPool(n_jobs=n_jobs, shared_objects=shared, use_worker_state=True, keep_alive=True) as pool:

                self.assertListEqual(pool.map(self._f1, self.test_data), self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs)
                barrier.reset()

                self.assertListEqual(list(pool.imap(self._f1, self.test_data)), self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs)
                barrier.reset()

                self.assertListEqual(pool.map(self._f1, self.test_data), self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs)

    def test_keep_alive_func_changes(self):
        """
        When keep_alive is set to True it should reuse existing workers between map calls, but only when the called
        function is kept constant
        """
        for n_jobs in [1, 2, 4]:
            barrier = Barrier(n_jobs)
            counter = Value('i', 0)
            shared = barrier, counter
            with self.subTest(n_jobs=n_jobs), \
                    WorkerPool(n_jobs=n_jobs, shared_objects=shared, use_worker_state=True, keep_alive=True) as pool:

                self.assertListEqual(pool.map(self._f1, self.test_data), self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs)
                barrier.reset()

                self.assertListEqual(list(pool.imap(self._f2, self.test_data)), self.test_desired_output_f2)
                self.assertEqual(counter.value, n_jobs * 2)
                barrier.reset()

                self.assertListEqual(pool.map(self._f2, self.test_data), self.test_desired_output_f2)
                self.assertEqual(counter.value, n_jobs * 2)
                barrier.reset()

                self.assertListEqual(pool.map(self._f1, self.test_data), self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs * 3)

    def test_keep_alive_worker_lifespan_changes(self):
        """
        When keep_alive is set to True it should reuse existing workers between map calls, but only when the called
        function is kept constant
        """
        for n_jobs in [1, 2, 4]:
            barrier = Barrier(n_jobs)
            counter = Value('i', 0)
            shared = barrier, counter
            with self.subTest(n_jobs=n_jobs), \
                    WorkerPool(n_jobs=n_jobs, shared_objects=shared, use_worker_state=True, keep_alive=True) as pool:

                self.assertListEqual(pool.map(self._f1, self.test_data, worker_lifespan=100),
                                     self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs)
                barrier.reset()

                self.assertListEqual(list(pool.imap(self._f1, self.test_data, worker_lifespan=100)),
                                     self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs)
                barrier.reset()

                self.assertListEqual(pool.map(self._f1, self.test_data, worker_lifespan=200),
                                     self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs * 2)
                barrier.reset()

                self.assertListEqual(pool.map(self._f1, self.test_data, worker_lifespan=200),
                                     self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs * 2)
                barrier.reset()

                self.assertListEqual(pool.map(self._f1, self.test_data, worker_lifespan=100),
                                     self.test_desired_output_f1)
                self.assertEqual(counter.value, n_jobs * 3)

    @staticmethod
    def _f1(shared, worker_state, x):
        """
        Function that waits for all workers to spin up and increases the counter by one only once per worker,
        returns x * 2
        """
        barrier, counter = shared
        if 'already_counted' not in worker_state:
            with counter.get_lock():
                counter.value += 1
            worker_state['already_counted'] = True
            barrier.wait()
        return x * 2

    @staticmethod
    def _f2(shared, worker_state, x):
        """
        Function that waits for all workers to spin up and increases the counter by one only once per worker,
        returns x * 3
        """
        barrier, counter = shared
        if 'already_counted' not in worker_state:
            with counter.get_lock():
                counter.value += 1
            worker_state['already_counted'] = True
            barrier.wait()
        return x * 3


class ExceptionTest(unittest.TestCase):

    def setUp(self):
        # Create some test data. Note that the regular map reads the inputs as a list of single tuples (one argument),
        # whereas parallel.map sees it as a list of argument lists. Therefore we give the regular map a lambda function
        # which mimics the parallel.map behavior.
        self.test_data = list(enumerate([1, 2, 3, 5, 6, 9, 37, 42, 1337, 0, 3, 5, 0]))
        self.test_desired_output = list(map(lambda _args: square(*_args), self.test_data))
        self.test_data_len = len(self.test_data)

    def test_exceptions(self):
        """
        Tests if MPIRE can handle exceptions well
        """
        # This print statement is intentional as it will print multiple progress bars
        print()
        for n_jobs, n_tasks_max_active, worker_lifespan, progress_bar in product([1, 20], [None, 1], [None, 1],
                                                                                 [False, True]):
            with WorkerPool(n_jobs=n_jobs) as pool:

                # Should work for map like functions
                with self.subTest(n_jobs=n_jobs, n_tasks_max_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                  progress_bar=progress_bar, function='square_raises', map='map'), \
                     self.assertRaises(ValueError):
                    pool.map(self._square_raises, self.test_data, max_tasks_active=n_tasks_max_active,
                             worker_lifespan=worker_lifespan, progress_bar=progress_bar)

                # Should work for imap like functions
                with self.subTest(n_jobs=n_jobs, n_tasks_max_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                  progress_bar=progress_bar, function='square_raises', map='imap'), \
                     self.assertRaises(ValueError):
                    list(pool.imap_unordered(self._square_raises, self.test_data, max_tasks_active=n_tasks_max_active,
                                             worker_lifespan=worker_lifespan, progress_bar=progress_bar))

                # Should work for map like functions
                with self.subTest(n_jobs=n_jobs, n_tasks_max_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                  progress_bar=progress_bar, function='square_raises_on_idx', map='map'), \
                     self.assertRaises(ValueError):
                    pool.map(self._square_raises_on_idx, self.test_data, max_tasks_active=n_tasks_max_active,
                             worker_lifespan=worker_lifespan, progress_bar=progress_bar)

                # Should work for imap like functions
                with self.subTest(n_jobs=n_jobs, n_tasks_max_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                  progress_bar=progress_bar, function='square_raises_on_idx', map='imap'), \
                     self.assertRaises(ValueError):
                    list(pool.imap_unordered(self._square_raises_on_idx, self.test_data,
                                             max_tasks_active=n_tasks_max_active, worker_lifespan=worker_lifespan,
                                             progress_bar=progress_bar))

    @staticmethod
    def _square_raises(_, x):
        raise ValueError(x)

    @staticmethod
    def _square_raises_on_idx(idx, x):
        if idx == 5:
            raise ValueError(x)
        else:
            return idx, x * x


class InsightsTest(unittest.TestCase):

    def setUp(self):
        # Create some test data. Note that the regular map reads the inputs as a list of single tuples (one argument),
        # whereas parallel.map sees it as a list of argument lists. Therefore we give the regular map a lambda function
        # which mimics the parallel.map behavior.
        self.test_data = list(enumerate([1, 2, 3, 5, 6, 9, 37, 42, 1337, 0, 3, 5, 0]))
        self.test_desired_output = list(map(lambda _args: square(*_args), self.test_data))
        self.test_data_len = len(self.test_data)
        self.test_data_args = {' | '.join(f"Arg {idx}: {repr(arg)}" for idx, arg in enumerate(args))
                               for args in self.test_data}

    def test_reset_insights(self):
        """
        Test if resetting the insights is done properly
        """
        for n_jobs in [1, 2, 4]:
            with WorkerPool(n_jobs=n_jobs) as pool:

                with self.subTest('initialized', n_jobs=n_jobs):
                    self.assertIsNone(pool.insights_manager)
                    self.assertIsNone(pool.worker_start_up_time)
                    self.assertIsNone(pool.worker_init_time)
                    self.assertIsNone(pool.worker_n_completed_tasks)
                    self.assertIsNone(pool.worker_waiting_time)
                    self.assertIsNone(pool.worker_working_time)
                    self.assertIsNone(pool.worker_exit_time)
                    self.assertIsNone(pool.max_task_duration)
                    self.assertIsNone(pool.max_task_args)

                # Containers should be properly initialized
                with self.subTest('without initial values', n_jobs=n_jobs, enable_insights=True):
                    pool._reset_insights(enable_insights=True)
                    self.assertIsInstance(pool.insights_manager, managers.SyncManager)
                    self.assertIsInstance(pool.worker_start_up_time, ctypes.Array)
                    self.assertIsInstance(pool.worker_init_time, ctypes.Array)
                    self.assertIsInstance(pool.worker_n_completed_tasks, ctypes.Array)
                    self.assertIsInstance(pool.worker_waiting_time, ctypes.Array)
                    self.assertIsInstance(pool.worker_working_time, ctypes.Array)
                    self.assertIsInstance(pool.worker_exit_time, ctypes.Array)
                    self.assertIsInstance(pool.max_task_duration, ctypes.Array)
                    self.assertIsInstance(pool.max_task_args, managers.ListProxy)

                    # Basic sanity checks for the values
                    self.assertEqual(sum(pool.worker_start_up_time), 0)
                    self.assertEqual(sum(pool.worker_init_time), 0)
                    self.assertEqual(sum(pool.worker_n_completed_tasks), 0)
                    self.assertEqual(sum(pool.worker_waiting_time), 0)
                    self.assertEqual(sum(pool.worker_working_time), 0)
                    self.assertEqual(sum(pool.worker_exit_time), 0)
                    self.assertEqual(sum(pool.max_task_duration), 0)
                    self.assertListEqual(list(pool.max_task_args), [''] * n_jobs * 5)

                # Execute something so we can test if the containers will be properly resetted
                pool.map(square, self.test_data)

                # Containers should be properly initialized
                with self.subTest('with initial values', n_jobs=n_jobs, enable_insights=True):
                    pool._reset_insights(enable_insights=True)
                    # Basic sanity checks for the values
                    self.assertEqual(sum(pool.worker_start_up_time), 0)
                    self.assertEqual(sum(pool.worker_init_time), 0)
                    self.assertEqual(sum(pool.worker_n_completed_tasks), 0)
                    self.assertEqual(sum(pool.worker_waiting_time), 0)
                    self.assertEqual(sum(pool.worker_working_time), 0)
                    self.assertEqual(sum(pool.worker_exit_time), 0)
                    self.assertEqual(sum(pool.max_task_duration), 0)
                    self.assertListEqual(list(pool.max_task_args), [''] * n_jobs * 5)

                # Disabling should set things to None again
                with self.subTest(n_jobs=n_jobs, enable_insights=False):
                    pool._reset_insights(enable_insights=False)
                    self.assertIsNone(pool.insights_manager)
                    self.assertIsNone(pool.worker_start_up_time)
                    self.assertIsNone(pool.worker_init_time)
                    self.assertIsNone(pool.worker_n_completed_tasks)
                    self.assertIsNone(pool.worker_waiting_time)
                    self.assertIsNone(pool.worker_working_time)
                    self.assertIsNone(pool.worker_exit_time)
                    self.assertIsNone(pool.max_task_duration)
                    self.assertIsNone(pool.max_task_args)

    def test_enable_insights(self):
        """
        Insight containers are initially set to None values. When enabled they should be changed to appropriate
        containers. When a second task is started it should reset them. If disabled, they should remain None
        """
        with WorkerPool(n_jobs=2) as pool:

            # We run this a few times to see if it resets properly. We only verify this by checking the
            # n_completed_tasks
            for idx in range(3):
                with self.subTest('enabled', idx=idx):

                    self.assertListEqual(pool.map(square, self.test_data, enable_insights=True, worker_init=self._init,
                                                  worker_exit=self._exit),
                                         self.test_desired_output)

                    # Basic sanity checks for the values. Some max task args can be empty, in that case the duration
                    # should be 0 (= no data)
                    self.assertGreater(sum(pool.worker_start_up_time), 0)
                    self.assertGreater(sum(pool.worker_init_time), 0)
                    self.assertEqual(sum(pool.worker_n_completed_tasks), self.test_data_len)
                    self.assertGreater(sum(pool.worker_waiting_time), 0)
                    self.assertGreater(sum(pool.worker_working_time), 0)
                    self.assertGreater(sum(pool.worker_exit_time), 0)
                    self.assertGreater(max(pool.max_task_duration), 0)
                    for duration, args in zip(pool.max_task_duration, pool.max_task_args):
                        if duration == 0:
                            self.assertEqual(args, '')
                        else:
                            self.assertIn(args, self.test_data_args)

            # Disabling should set things to None again
            with self.subTest('disable'):
                self.assertListEqual(pool.map(square, self.test_data, enable_insights=False), self.test_desired_output)
                self.assertIsNone(pool.insights_manager)
                self.assertIsNone(pool.worker_start_up_time)
                self.assertIsNone(pool.worker_init_time)
                self.assertIsNone(pool.worker_n_completed_tasks)
                self.assertIsNone(pool.worker_waiting_time)
                self.assertIsNone(pool.worker_working_time)
                self.assertIsNone(pool.worker_exit_time)
                self.assertIsNone(pool.max_task_duration)
                self.assertIsNone(pool.max_task_args)

    def test_get_insights(self):
        """
        Test if the insights are properly processed
        """
        with WorkerPool(n_jobs=2) as pool:

            with self.subTest(enable_insights=False):
                pool._reset_insights(enable_insights=False)
                self.assertDictEqual(pool.get_insights(), {})

            with self.subTest(enable_insights=True):
                pool._reset_insights(enable_insights=True)
                pool.worker_start_up_time[:] = [0.1, 0.2]
                pool.worker_init_time[:] = [0.11, 0.22]
                pool.worker_n_completed_tasks[:] = [2, 3]
                pool.worker_waiting_time[:] = [0.4, 0.3]
                pool.worker_working_time[:] = [42.0, 37.0]
                pool.worker_exit_time[:] = [0.33, 0.44]

                # Durations that are zero or args that are empty are skipped
                pool.max_task_duration[:] = [0.0, 0.0, 1.0, 2.0, 0.0, 6.0, 0.8, 0.0, 0.1, 0.0]
                pool.max_task_args[:] = ['', '', '1', '2', '', '3', '4', '', '5', '']
                insights = pool.get_insights()

                # Test ratios separately because of rounding errors
                total_time = 0.3 + 0.33 + 0.7 + 79.0 + 0.77
                self.assertAlmostEqual(insights['start_up_ratio'], 0.3 / total_time)
                self.assertAlmostEqual(insights['init_ratio'], 0.33 / total_time)
                self.assertAlmostEqual(insights['waiting_ratio'], 0.7 / total_time)
                self.assertAlmostEqual(insights['working_ratio'], 79.0 / total_time)
                self.assertAlmostEqual(insights['exit_ratio'], 0.77 / total_time)
                del (insights['start_up_ratio'], insights['init_ratio'], insights['waiting_ratio'],
                     insights['working_ratio'], insights['exit_ratio'])

                self.assertDictEqual(insights, {
                    'n_completed_tasks': [2, 3],
                    'start_up_time': ['0:00:00.100', '0:00:00.200'],
                    'init_time': ['0:00:00.110', '0:00:00.220'],
                    'waiting_time': ['0:00:00.400', '0:00:00.300'],
                    'working_time': ['0:00:42', '0:00:37'],
                    'exit_time': ['0:00:00.330', '0:00:00.440'],
                    'total_start_up_time': '0:00:00.300',
                    'total_init_time': '0:00:00.330',
                    'total_waiting_time': '0:00:00.700',
                    'total_working_time': '0:01:19',
                    'total_exit_time': '0:00:00.770',
                    'top_5_max_task_durations': ['0:00:06', '0:00:02', '0:00:01', '0:00:00.800', '0:00:00.100'],
                    'top_5_max_task_args': ['3', '2', '1', '4', '5'],
                    'total_time': '0:01:21.100',
                    'start_up_time_mean': '0:00:00.150', 'start_up_time_std': '0:00:00.050',
                    'init_time_mean': '0:00:00.165', 'init_time_std': '0:00:00.055',
                    'waiting_time_mean': '0:00:00.350', 'waiting_time_std': '0:00:00.050',
                    'working_time_mean': '0:00:39.500', 'working_time_std': '0:00:02.500',
                    'exit_time_mean': '0:00:00.385', 'exit_time_std': '0:00:00.055'
                })

    @staticmethod
    def _init():
        # It's just here so we have something to time
        _ = [x**x for x in range(1000)]

    @staticmethod
    def _exit():
        # It's just here so we have something to time
        return [x ** x for x in range(1000)]
