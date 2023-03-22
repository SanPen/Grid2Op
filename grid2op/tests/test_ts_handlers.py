# Copyright (c) 2019-2023, RTE (https://www.rte-france.com)
# See AUTHORS.txt
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
# you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of Grid2Op, Grid2Op a testbed platform to model sequential decision making in power systems.

import copy
import pdb
import time
import warnings

from grid2op.tests.helper_path_test import *

import grid2op
from grid2op.Chronics import GridStateFromFileWithForecasts, GridStateFromFile, GridStateFromFileWithForecastsWithoutMaintenance
from grid2op.Chronics.time_series_from_handlers import FromHandlers
from grid2op.Chronics.handlers import (CSVHandler,
                                       DoNothingHandler,
                                       CSVHandlerForecast,
                                       CSVHandlerMaintenance,
                                       JSONHandlerMaintenance,
                                       )
from grid2op.Runner import Runner
from grid2op.Exceptions import HandlerError
from grid2op.Parameters import Parameters

import warnings

# TODO check when there is also redispatching


def _load_next_chunk_in_memory_hack(self):
    self._nb_call += 1
    # i load the next chunk as dataframes
    array = self._get_next_chunk()  # array: load_p
    # i put these dataframes in the right order (columns)
    self._init_attrs(array)  # TODO
    # i don't forget to reset the reading index to 0
    self.current_index = 0
        
class TestCSVHandlerEnv(HelperTests):
    """test the env part of the storage functionality"""
    def _aux_assert_right_type_chronics(self):
        assert isinstance(self.env1.chronics_handler.real_data.data, GridStateFromFile)
        assert isinstance(self.env2.chronics_handler.real_data.data, FromHandlers)
        
    def _aux_reproducibility(self):
        for env in [self.env1, self.env2]:
            env.set_id(0)
            env.seed(0)
            env.reset()
        self._aux_assert_right_type_chronics()
        
    def setUp(self) -> None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            self.env1 = grid2op.make("l2rpn_case14_sandbox", test=True)  # regular env
            self.env2 = grid2op.make("l2rpn_case14_sandbox",
                                     data_feeding_kwargs={"gridvalueClass": FromHandlers,
                                                          "gen_p_handler": CSVHandler("prod_p"),
                                                          "load_p_handler": CSVHandler("load_p"),
                                                          "gen_v_handler": CSVHandler("prod_v"),
                                                          "load_q_handler": CSVHandler("load_q"),
                                                          },
                                     _add_to_name="_TestCSVHandlerEnv",
                                     test=True)  # regular env
        self._aux_reproducibility()
        return super().setUp()

    def tearDown(self) -> None:
        self.env1.close()
        self.env2.close()
        return super().tearDown()

    def _aux_compare_one(self, it_nm, obs1, obs2, descr=""):
        for attr_nm in ["load_p", "load_q", "gen_v", "rho", "gen_p", "line_status", "time_next_maintenance"]:
            # assert np.all(getattr(obs1, attr_nm) == getattr(obs2, attr_nm)), f"error for {attr_nm}{descr} at iteration {it_nm}: {getattr(obs1, attr_nm)} vs {getattr(obs2, attr_nm)}"
            assert np.allclose(getattr(obs1, attr_nm), getattr(obs2, attr_nm)), f"error for {attr_nm}{descr} at iteration {it_nm}: {getattr(obs1, attr_nm)} vs {getattr(obs2, attr_nm)}"
    
    def _run_then_compare(self, nb_iter=10, env1=None, env2=None):
        if env1 is None:
            env1 = self.env1
        if env2 is None:
            env2 = self.env2
            
        for k in range(nb_iter):
            obs1, reward1, done1, info1 = env1.step(env1.action_space())
            obs2, reward2, done2, info2 = env2.step(env2.action_space())
            assert done2 == done1, f"error at iteration {k} for done"
            assert reward1 == reward2, f"error at iteration {k} for reward"
            if done1:
                break
            self._aux_compare_one(k, obs1, obs2)
                
    def test_step_equal(self):
        self._run_then_compare()
        self.env1.reset()
        self.env2.reset()
        self._run_then_compare()
        self.env1.reset()
        self.env2.reset()
        self._run_then_compare()
    
    def test_max_iter(self):
        self.env1.set_max_iter(5)
        self.env2.set_max_iter(5)
        
        self.env1.reset()
        self.env2.reset()
        self._run_then_compare(nb_iter=4)
        
        obs1, reward1, done1, info1 = self.env1.step(self.env1.action_space())
        obs2, reward2, done2, info2 = self.env2.step(self.env2.action_space())
        assert done1
        assert done2
        
    def test_chunk(self):
        self.env_ref = self.env1.copy()
        
        self.env1.set_chunk_size(1)
        self.env2.set_chunk_size(1)
        
        # hugly copy paste from above otherwise the hack does not work...
        # because of the reset
        self.env1.set_max_iter(5)
        self.env2.set_max_iter(5)
        self.env_ref.set_max_iter(5)
        obs1 = self.env1.reset()
        obs2 = self.env2.reset()
        self.env_ref.reset()
        self._aux_compare_one(0, obs1, obs2)
        
        ###### hack to count the number this is called
        if hasattr(self.env2.chronics_handler.real_data, "data"):
            self.env2.chronics_handler.data.gen_p_handler._nb_call = 0
            self.env2.chronics_handler.data.gen_p_handler._load_next_chunk_in_memory = lambda : _load_next_chunk_in_memory_hack(self.env2.chronics_handler.data.gen_p_handler)
        else:
            self.env2.chronics_handler.gen_p_handler._nb_call = 0
            self.env2.chronics_handler.gen_p_handler._load_next_chunk_in_memory = lambda : _load_next_chunk_in_memory_hack(self.env2.chronics_handler.gen_p_handler)
        ######
        
        self._run_then_compare(nb_iter=4)
        
        obs1, reward1, done1, info1 = self.env1.step(self.env1.action_space())
        obs2, reward2, done2, info2 = self.env2.step(self.env2.action_space())
        assert done1
        assert done2
        
        # now check the "load_next_chunk has been called the right number of time"
        if hasattr(self.env2.chronics_handler.real_data, "data"):
            assert self.env2.chronics_handler.data.gen_p_handler._nb_call == 5
        else:
            assert self.env2.chronics_handler.gen_p_handler._nb_call == 5
        
    def test_copy(self):
        env2 = self.env2.copy()
        self._run_then_compare(env2=env2)
        self.env1.reset()
        env2.reset()
        self._run_then_compare(env2=env2)
        self.env1.reset()
        env2.reset()
        self._run_then_compare(env2=env2)   

    def test_runner(self):
        runner1 = Runner(**self.env1.get_params_for_runner())
        runner2 = Runner(**self.env2.get_params_for_runner())
        res1 = runner1.run(nb_episode=2, max_iter=5, env_seeds=[0, 1], episode_id=[0, 1])
        res2 = runner2.run(nb_episode=2, max_iter=5, env_seeds=[0, 1], episode_id=[0, 1])
        assert res1 == res2
    
    def test_if_file_absent(self):
        # do it only once
        if type(self) != TestCSVHandlerEnv:
            self.skipTest("This test should be done only in the TestCSVHandlerEnv class (no need to do it 10x times)")
        with self.assertRaises(HandlerError):
            grid2op.make(os.path.join(PATH_DATA_TEST, "5bus_example_some_missing"),
                         data_feeding_kwargs={"gridvalueClass": FromHandlers,
                                              "gen_p_handler": CSVHandler("prod_p"),
                                              "load_p_handler": CSVHandler("load_p"),
                                              "gen_v_handler": DoNothingHandler(),
                                              "load_q_handler": CSVHandler("load_q"), # crash because this file does not exist
                                              },
                         _add_to_name="_TestCSVHandlerEnv")  # regular env

    def test_max_episode_duration(self):
        assert self.env2.max_episode_duration() == self.env1.max_episode_duration()
        self.env1.reset()
        self.env2.reset()
        assert self.env2.max_episode_duration() == self.env1.max_episode_duration()
        self.env1.set_max_iter(5)
        self.env2.set_max_iter(5)
        self.env1.reset()
        self.env2.reset()
        assert self.env2.max_episode_duration() == self.env1.max_episode_duration()
        self.env1.set_chunk_size(1)
        self.env2.set_chunk_size(1)
        self.env1.reset()
        self.env2.reset()
        assert self.env2.max_episode_duration() == self.env1.max_episode_duration()
        
    def test_fast_forward_chronics(self):
        self.env1.fast_forward_chronics(5)
        self.env2.fast_forward_chronics(5)
        self._run_then_compare()
        self.env1.fast_forward_chronics(7)
        self.env2.fast_forward_chronics(7)
        self._run_then_compare()
        self.env1.reset()
        self.env2.reset()
        self._run_then_compare()
        
# TODO:
# test when "names_chronics_to_backend"
# test sample_next_chronics
# test I can "finish" an environment completely (without max_iter, when data are over)
# test multifolderwithCache

# test without "multi folder" X
# test runner X
# test env copy X
# test when max_iter `env.set_max_iter` X
# test when "set_chunk" X
# test with forecasts
# test next_chronics
# test tell_id
# test set_id
# test with maintenance
# test fast_forward_chronics


class TestSomeFileMissingEnv(TestCSVHandlerEnv):
    """test the env part of the storage functionality"""
    def setUp(self) -> None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            self.env1 = grid2op.make(os.path.join(PATH_DATA_TEST, "5bus_example_some_missing"))  # regular env
            self.env2 = grid2op.make(os.path.join(PATH_DATA_TEST, "5bus_example_some_missing"),
                                     data_feeding_kwargs={"gridvalueClass": FromHandlers,
                                                          "gen_p_handler": CSVHandler("prod_p"),
                                                          "load_p_handler": CSVHandler("load_p"),
                                                          "gen_v_handler": DoNothingHandler(),
                                                          "load_q_handler": DoNothingHandler(),
                                                          },
                                     _add_to_name="_TestDNHandlerEnv")
        self._aux_reproducibility()
        
        
class TestWithoutMultiFolderEnv(TestCSVHandlerEnv):
    def setUp(self) -> None:
        chronics_path = os.path.join(PATH_DATA,
                                     "l2rpn_case14_sandbox",
                                     "chronics",
                                     "0000")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            self.env1 = grid2op.make("l2rpn_case14_sandbox", test=True,
                                     chronics_class=GridStateFromFileWithForecasts,
                                     chronics_path=chronics_path)  # regular env
            self.env2 = grid2op.make("l2rpn_case14_sandbox",
                                     chronics_class=FromHandlers,
                                     data_feeding_kwargs={
                                                          "gen_p_handler": CSVHandler("prod_p"),
                                                          "load_p_handler": CSVHandler("load_p"),
                                                          "gen_v_handler": CSVHandler("prod_v"),
                                                          "load_q_handler": CSVHandler("load_q"),
                                                          },
                                     chronics_path=chronics_path,
                                     _add_to_name="TestWithoutMultiFolderEnv",
                                     test=True)
        self._aux_reproducibility()
        
    def _aux_assert_right_type_chronics(self):
        assert isinstance(self.env1.chronics_handler.real_data, GridStateFromFile)
        assert isinstance(self.env2.chronics_handler.real_data, FromHandlers)
            
            
class TestForecastHandlerNoMultiFolder(TestWithoutMultiFolderEnv):
    """test the env part of the storage functionality"""
    def setUp(self) -> None:
        chronics_path = os.path.join(PATH_DATA,
                                     "l2rpn_case14_sandbox",
                                     "chronics",
                                     "0000")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            self.env1 = grid2op.make("l2rpn_case14_sandbox", test=True,
                                     chronics_class=GridStateFromFileWithForecasts,
                                     chronics_path=chronics_path)  # regular env
            self.env2 = grid2op.make("l2rpn_case14_sandbox",
                                     chronics_class=FromHandlers,
                                     data_feeding_kwargs={"gen_p_handler": CSVHandler("prod_p"),
                                                          "load_p_handler": CSVHandler("load_p"),
                                                          "gen_v_handler": CSVHandler("prod_v"),
                                                          "load_q_handler": CSVHandler("load_q"),
                                                          "gen_p_for_handler": CSVHandlerForecast("prod_p_forecasted"),
                                                          "load_p_for_handler": CSVHandlerForecast("load_p_forecasted"),
                                                          "gen_v_for_handler": CSVHandlerForecast("prod_v_forecasted"),
                                                          "load_q_for_handler": CSVHandlerForecast("load_q_forecasted"),
                                                          },
                                     chronics_path=chronics_path,
                                     _add_to_name="TestForecastHandlerNoMulti14",
                                     test=True)
        self._aux_reproducibility()
        assert np.all(self.env1.chronics_handler.real_data.load_p_forecast == 
                      self.env2.chronics_handler.real_data.load_p_for_handler.array)
            
    def _aux_compare_one(self, it_nm, obs1, obs2):
        super()._aux_compare_one(it_nm, obs1, obs2)
        sim_obs1, *_ = obs1.simulate(self.env1.action_space())
        sim_obs2, *_ = obs2.simulate(self.env1.action_space())
        super()._aux_compare_one(it_nm, sim_obs1, sim_obs2, " forecast")
        
            
class TestForecastHandler14(TestCSVHandlerEnv):
    def setUp(self) -> None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            self.env1 = grid2op.make("l2rpn_case14_sandbox", test=True)  # regular env
            self.env2 = grid2op.make("l2rpn_case14_sandbox",
                                     data_feeding_kwargs={"gridvalueClass": FromHandlers,
                                                          "gen_p_handler": CSVHandler("prod_p"),
                                                          "load_p_handler": CSVHandler("load_p"),
                                                          "gen_v_handler": CSVHandler("prod_v"),
                                                          "load_q_handler": CSVHandler("load_q"),
                                                          "gen_p_for_handler": CSVHandlerForecast("prod_p_forecasted"),
                                                          "load_p_for_handler": CSVHandlerForecast("load_p_forecasted"),
                                                          "gen_v_for_handler": CSVHandlerForecast("prod_v_forecasted"),
                                                          "load_q_for_handler": CSVHandlerForecast("load_q_forecasted"),
                                                          },
                                     _add_to_name="TestForecastHandlerEnv",
                                     test=True)
        self._aux_reproducibility()
        assert np.all(self.env1.chronics_handler.real_data.data.load_p_forecast == 
                      self.env2.chronics_handler.real_data.data.load_p_for_handler.array)
        
            
    def _aux_compare_one(self, it_nm, obs1, obs2):
        super()._aux_compare_one(it_nm, obs1, obs2)
        sim_obs1, *_ = obs1.simulate(self.env1.action_space())
        sim_obs2, *_ = obs2.simulate(self.env1.action_space())
        super()._aux_compare_one(it_nm, sim_obs1, sim_obs2, " forecast")
            
            
class TestForecastHandler5MultiSteps(TestCSVHandlerEnv):
    def setUp(self) -> None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            self.env1 = grid2op.make(os.path.join(PATH_DATA_TEST, "5bus_example_forecasts"), test=True,
                                     data_feeding_kwargs={"gridvalueClass": GridStateFromFileWithForecastsWithoutMaintenance},
                                     )  # regular env
            self.env2 = grid2op.make(os.path.join(PATH_DATA_TEST, "5bus_example_forecasts"),
                                     data_feeding_kwargs={"gridvalueClass": FromHandlers,
                                                          "gen_p_handler": CSVHandler("prod_p"),
                                                          "load_p_handler": CSVHandler("load_p"),
                                                          "load_q_handler": CSVHandler("load_q"),
                                                          "gen_v_handler": DoNothingHandler(),
                                                          "gen_p_for_handler": CSVHandlerForecast("prod_p_forecasted"),
                                                          "load_p_for_handler": CSVHandlerForecast("load_p_forecasted"),
                                                          "load_q_for_handler": CSVHandlerForecast("load_q_forecasted"),
                                                          },
                                     _add_to_name="TestForecastHandler5MultiSteps",
                                     test=True)
        self._aux_reproducibility()
        assert np.all(self.env1.chronics_handler.real_data.data.load_p == 
                      self.env2.chronics_handler.real_data.data.load_p_handler.array)
        assert np.all(self.env1.chronics_handler.real_data.data.load_p_forecast == 
                      self.env2.chronics_handler.real_data.data.load_p_for_handler.array)
        assert np.all(self.env1.chronics_handler.real_data.data.prod_p == 
                      self.env2.chronics_handler.real_data.data.gen_p_handler.array)
        assert np.all(self.env1.chronics_handler.real_data.data.prod_p_forecast == 
                      self.env2.chronics_handler.real_data.data.gen_p_for_handler.array)
        
    def _aux_compare_one(self, it_nm, obs1, obs2):
        super()._aux_compare_one(it_nm, obs1, obs2)
        sim_obs1_1, *_ = obs1.simulate(self.env1.action_space())
        sim_obs2_1, *_ = obs2.simulate(self.env1.action_space())
        super()._aux_compare_one(it_nm, sim_obs1_1, sim_obs2_1, " forecast 1")
        
        sim_obs1_2, *_ = sim_obs1_1.simulate(self.env1.action_space())
        sim_obs2_2, *_ = sim_obs2_1.simulate(self.env1.action_space())
        super()._aux_compare_one(it_nm, sim_obs1_2, sim_obs2_2, " forecast 2")
        
        sim_obs1_3, *_ = sim_obs1_2.simulate(self.env1.action_space())
        sim_obs2_3, *_ = sim_obs2_2.simulate(self.env1.action_space())
        super()._aux_compare_one(it_nm, sim_obs1_3, sim_obs2_3, " forecast 3")


class TestMaintenanceCSV(TestForecastHandler14):
    def setUp(self) -> None:
        param = Parameters()
        param.NO_OVERFLOW_DISCONNECTION = True
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            self.env1 = grid2op.make(os.path.join(PATH_DATA_TEST, "env_14_test_maintenance"),
                                     test=True,
                                     param=param
                                     )  # regular env
            self.env2 = grid2op.make(os.path.join(PATH_DATA_TEST, "env_14_test_maintenance"),
                                     data_feeding_kwargs={"gridvalueClass": FromHandlers,
                                                          "gen_p_handler": CSVHandler("prod_p"),
                                                          "load_p_handler": CSVHandler("load_p"),
                                                          "load_q_handler": CSVHandler("load_q"),
                                                          "gen_v_handler": CSVHandler("prod_v"),
                                                          "maintenance_handler": CSVHandlerMaintenance(),
                                                          "gen_p_for_handler": CSVHandlerForecast("prod_p_forecasted"),
                                                          "gen_v_for_handler": CSVHandlerForecast("prod_v_forecasted"),
                                                          "load_p_for_handler": CSVHandlerForecast("load_p_forecasted"),
                                                          "load_q_for_handler": CSVHandlerForecast("load_q_forecasted"),
                                                          },
                                     _add_to_name="TestMaintenanceCSV",
                                     test=True,
                                     param=param)
        self._aux_reproducibility()
        assert np.all(self.env1.chronics_handler.real_data.data.maintenance == 
                      self.env2.chronics_handler.real_data.data.maintenance_handler.array)
        assert np.all(self.env1.chronics_handler.real_data.data.maintenance_time == 
                      self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance_time)
        assert np.all(self.env1.chronics_handler.real_data.data.maintenance_duration == 
                      self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance_duration)


class TestMaintenanceJson(unittest.TestCase):
    def setUp(self) -> None:        
        param = Parameters()
        param.NO_OVERFLOW_DISCONNECTION = True
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            self.env2 = grid2op.make(os.path.join(PATH_DATA_TEST, "ieee118_R2subgrid_wcci_test_maintenance"),
                                     data_feeding_kwargs={"gridvalueClass": FromHandlers,
                                                          "gen_p_handler": CSVHandler("prod_p"),
                                                          "load_p_handler": CSVHandler("load_p"),
                                                          "load_q_handler": CSVHandler("load_q"),
                                                          "gen_v_handler": CSVHandler("prod_v"),
                                                          "maintenance_handler": JSONHandlerMaintenance(),
                                                          "gen_p_for_handler": CSVHandlerForecast("prod_p_forecasted"),
                                                          "load_p_for_handler": CSVHandlerForecast("load_p_forecasted"),
                                                          "load_q_for_handler": CSVHandlerForecast("load_q_forecasted"),
                                                          },
                                     _add_to_name="TestMaintenanceCSV",
                                     test=True,
                                     param=param)
        # carefull here ! the "seed" mechanism does not work the same way between the two alternative.
        # in the second case each "handler" get its own prng with a different seed. This is
        # why you cannot compare directly the generated maintenance between the two env and why
        # this does not inherit from TestCSVHandlerEnv 

    def tearDown(self) -> None:
        self.env2.close()
        return super().tearDown()
    
    def test_seed(self):
        self.env2.seed(0)
        self.env2.reset()
        all_ln_nm = np.zeros(type(self.env2).n_line, dtype=bool)
        assert self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance.sum() == 960
        tmp_ = np.where(self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance.any(axis=0))[0]
        assert np.all(tmp_ == [ 0,  9, 14, 27, 45, 56])
        all_ln_nm[tmp_] = True
        self.env2.reset()
        assert self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance.sum() == 1248
        tmp_ = np.where(self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance.any(axis=0))[0]
        assert np.all(tmp_ == [ 0, 13, 14, 18, 23, 27, 39, 45, 56])
        all_ln_nm[tmp_] = True
        self.env2.reset()
        assert self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance.sum() == 960
        tmp_ = np.where(self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance.any(axis=0))[0]
        assert np.all(tmp_ == [13, 14, 23, 27, 45])
        all_ln_nm[tmp_] = True
        self.env2.reset()
        assert self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance.sum() == 672
        tmp_ = np.where(self.env2.chronics_handler.real_data.data.maintenance_handler.maintenance.any(axis=0))[0]
        assert np.all(tmp_ == [ 0,  9, 13, 18, 23, 56])
        all_ln_nm[tmp_] = True
        
        line_to_maintenance = self.env2.chronics_handler.real_data.data.maintenance_handler.dict_meta_data["line_to_maintenance"]
        assert np.all(np.isin(type(self.env2).name_line[all_ln_nm], line_to_maintenance))
        assert np.all(np.isin(line_to_maintenance, type(self.env2).name_line[all_ln_nm]))
        
        
if __name__ == "__main__":
    unittest.main()
