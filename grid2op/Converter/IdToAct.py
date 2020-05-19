# Copyright (c) 2019-2020, RTE (https://www.rte-france.com)
# See AUTHORS.txt
# This Source Code Form is subject to the terms of the Mozilla Public License, version 2.0.
# If a copy of the Mozilla Public License, version 2.0 was not distributed with this file,
# you can obtain one at http://mozilla.org/MPL/2.0/.
# SPDX-License-Identifier: MPL-2.0
# This file is part of Grid2Op, Grid2Op a testbed platform to model sequential decision making in power systems.
import os
import numpy as np

from grid2op.Action import BaseAction
from grid2op.Converter.Converters import Converter
from grid2op.dtypes import dt_float
import pdb


class IdToAct(Converter):
    """
    This type of converter allows to represent action with unique id. Instead of manipulating complex objects, it allows
    to manipulate only positive integer.

    The list of all actions can either be the list of all possible unary actions (see below for a complete
    description) or by a given pre computed list.

    A "unary action" is an action that consists only in acting on one "concept" it includes:

    - disconnecting a single powerline
    - reconnecting a single powerline and connect it to bus xxx on its origin end and yyy on its extremity end
    - changing the topology of a single substation

    Examples of non unary actions include:
    - disconnection / reconnection of 2 or more powerlines
    - change of the configuration of 2 or more substations
    - disconnection / reconnection of a single powerline and change of the configration of a single substation

    **NB** All the actions created automatically are unary. For the L2RPN 2019, agent could be allowed to act with non
    unary actions, for example by disconnecting a powerline and reconfiguring a substation. This class would not
    allow to do such action at one time step.

    **NB** The actions that are initialized by default uses the "set" way and not the "change" way (see the description
    of :class:`grid2op.BaseAction.BaseAction` for more information).

    For each powerline, 5 different actions will be computed:

    - disconnect it
    - reconnect it and connect it to bus 1 on "origin" end ann bus 1 on "extremity" end
    - reconnect it and connect it to bus 1 on "origin" end ann bus 2 on "extremity" end
    - reconnect it and connect it to bus 2 on "origin" end ann bus 1 on "extremity" end
    - reconnect it and connect it to bus 2 on "origin" end ann bus 2 on "extremity" end

    Actions corresponding to all topologies are also used by default. See
    :func:`grid2op.BaseAction.ActionSpace.get_all_unitary_topologies_set` for more information.


    In this converter:

    - `encoded_act` are positive integer, representing the index of the actions.
    - `transformed_obs` are regular observations.


    **NB** The number of actions in this converter can be especially big. For example, if a substation counts N elements
    there are roughly 2^(N-1) possible actions in this substation. This means if there are a single substation with
    more than N = 15 or 16 elements, the amount of actions (for this substation alone) will be higher than 16.000
    which makes it rather difficult to handle for most machine learning algorithm. Be carefull with that !

    """
    def __init__(self, action_space):
        Converter.__init__(self, action_space)
        self.__class__ = IdToAct.init_grid(action_space)
        self.all_actions = []
        # add the do nothing topology
        self.all_actions.append(super().__call__())
        self.n = 1

    def init_converter(self, all_actions=None, **kwargs):
        """
        This function is used to initialized the converter. When the converter is created, this method should be called
        otherwise the converter might be in an unstable state.

        Parameters
        ----------
        all_actions: ``list``
            The (ordered) list of all actions that the agent will be able to perform. If given a number ``i`` the
            converter will return action ``all_actions[i]``. In the "pacman" game, this vector could be
            ["up", "down", "left", "right"], in this case "up" would be encode by 0, "down" by 1, "left" by 2 and
            "right" by 3. If nothing is provided, the converter will output all the unary actions possible for
            the environment. Be careful, computing all these actions might take some time.

        kwargs:
            other keyword arguments (all considered to be ``True`` by default) that can be:

            set_line_status: ``bool``
                Whether you want to include the set line status in your action
                (in case the original action space allows it)

            change_line_status: ``bool``
                Whether you want to include the "change line status" in your action space
                (in case the original action space allows it)

            change_line_status: ``bool``
                Whether you want to include the "change line status" in your action space
                (in case the original action space allows it)

            set_topo_vect: ``bool``
                Whether you want to include the "set_bus" in your action space
                (in case the original action space allows it)

            change_bus_vect: ``bool``
                Whether you want to include the "change_bus" in your action space
                (in case the original action space allows it)

            redispatch: ``bool``
                Whether you want to include the "redispatch" in your action space
                (in case the original action space allows it)

        """
        if all_actions is None:
            self.all_actions = []
            # add the do nothing action, always
            self.all_actions.append(super().__call__())
            if "_set_line_status" in self._template_act.attr_list_vect:
                # lines 'set'
                include_ = True
                if "set_line_status" in kwargs:
                    include_ = kwargs["set_line_status"]
                if include_:
                    self.all_actions += self.get_all_unitary_line_set(self)

            if "_switch_line_status" in self._template_act.attr_list_vect:
                # lines 'change'
                include_ = True
                if "change_line_status" in kwargs:
                    include_ = kwargs["change_line_status"]
                if include_:
                    self.all_actions += self.get_all_unitary_line_change(self)

            if "_set_topo_vect" in self._template_act.attr_list_vect:
                # topologies 'set'
                include_ = True
                if "set_topo_vect" in kwargs:
                    include_ = kwargs["set_topo_vect"]
                if include_:
                    self.all_actions += self.get_all_unitary_topologies_set(self)

            if "_change_bus_vect" in self._template_act.attr_list_vect:
                # topologies 'change'
                include_ = True
                if "change_bus_vect" in kwargs:
                    include_ = kwargs["change_bus_vect"]
                if include_:
                    self.all_actions += self.get_all_unitary_topologies_change(self)

            if "_redispatch" in self._template_act.attr_list_vect:
                # redispatch (transformed to discrete variables)
                include_ = True
                if "redispatch" in kwargs:
                    include_ = kwargs["redispatch"]
                if include_:
                    self.all_actions += self.get_all_unitary_redispatch(self)
        elif isinstance(all_actions, str):
            # load the path from the path provided
            if not os.path.exists(all_actions):
                raise FileNotFoundError("No file located at \"{}\" where the actions should have been stored."
                                        "".format(all_actions))
            try:
                all_act = np.load(all_actions)
            except Exception as e:
                raise RuntimeError("Impossible to load the data located at \"{}\" with error\n{}."
                                   "".format(all_actions, e))
            try:
                self.all_actions = np.array([super(Converter, self).from_vect(el) for el in all_act])
            except Exception as e:
                raise RuntimeError("Impossible to convert the data located at \"{}\" into valid grid2op action."
                                   "The error was:\n{}".format(all_actions, e))
        elif isinstance(all_actions, (list, np.ndarray)):
            # assign the action to my actions
            possible_act = all_actions[0]
            if isinstance(possible_act, BaseAction):
                self.all_actions = np.array(all_actions)
            else:
                try:
                    self.all_actions = np.array([super(Converter, self).from_vect(el) for el in all_actions])
                except Exception as e:
                    raise RuntimeError("Impossible to convert the data provided in \"all_actions\" into valid "
                                       "grid2op action. The error was:\n{}".format(e))
        else:
            raise RuntimeError("Impossible to load the action provided.")
        self.n = len(self.all_actions)

    def filter_action(self, filtering_fun):
        """
        This function allows you to "easily" filter generated actions.

        **NB** the action space will change after a call to this function, especially its size. It is NOT recommended
        to apply it once training has started.

        Parameters
        ----------
        filtering_fun: ``function``
            This takes an action as input and should retrieve ``True`` meaning "this action will be kept" or
            ``False`` meaning "this action will be dropped.

        """
        self.all_actions = np.array([el for el in self.all_actions if filtering_fun(el)])
        self.n = len(self.all_actions)

    def save(self, path, name="action_space_vect.npy"):
        """
        Save the action space as a numpy array that can be reloaded afterwards with the :func:`IdToAct.init_converter`
        function by setting argument `all_actions` to `os.path.join(path, name)`

        The resulting object will be a numpy array of float. Each row of this array will be an action of the
        action space.

        Parameters
        ----------
        path: ``str``
            The path were to save the action space

        name: ``str``, optional
            The name of the numpy array stored on disk. By default its "action_space_vect.npy"

        Returns
        -------

        """
        if not os.path.exists(path):
            raise FileNotFoundError("Impossible to save the action space as the directory \"{}\" does not exist."
                                    "".format(path))
        if not os.path.isdir(path):
            raise NotADirectoryError("The path to save the action space provided \"{}\" is not a directory."
                                     "".format(path))
        saved_npy = np.array([el.to_vect() for el in self.all_actions]).astype(dtype=dt_float).reshape(self.n, -1)
        np.save(file=os.path.join(path, name), arr=saved_npy)

    def sample(self):
        """
        Having define a complete set of observation an agent can do, sampling from it is now made easy.

        One action amoung the n possible actions is used at random.

        Returns
        -------
        res: ``int``
            An id of an action.

        """
        idx = self.space_prng.randint(0, self.n)
        return idx

    def convert_act(self, encoded_act):
        """
        In this converter, we suppose that "encoded_act" is an id of an action stored in the
        :attr:`IdToAct.all_actions` list.

        Converting an id of an action (here called "act") into a valid action is then easy: we just need to take the
        "act"-th element of :attr:`IdToAct.all_actions`.

        Parameters
        ----------
        encoded_act: ``int``
            The id of the action

        Returns
        -------
        action: :class:`grid2op.Action.Action`
            The action corresponding to id "act"
        """

        return self.all_actions[encoded_act]