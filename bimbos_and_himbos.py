# Licensed under WTFPLv3.1
#
#           DO WHAT THE FUCK YOU WANT TO PUBLIC LICENCE
# TERMS AND CONDITIONS FOR COPYING, DISTRIBUTION AND MODIFICATION
#
# 0. You just DO WHAT THE FUCK YOU WANT TO.
#

from functools import wraps
from inspect import ismethod
from math import isclose
from typing import Any, Callable

from protocolbuffers import PersistenceBlobs_pb2
from sims.aging.aging_mixin import AgingMixin
from sims.occult.occult_tracker import OccultTracker
from sims.sim_info import SimInfo
from sims.sim_info_types import Age, Gender, Species
from sims.sim_spawner import SimSpawner

import sims4.commands
import services


class Wrapper:
    """
    Helpers for wrapping class functions with custom code
    """
    @staticmethod
    def _wrap_helper(target_function, wrapper_function: Callable[..., Any]) -> Any:
        @wraps(target_function)
        def _wrapped_function(*args, **kwargs):
            if type(target_function) is property:
                return wrapper_function(target_function.fget, *args, **kwargs)
            return wrapper_function(target_function, *args, **kwargs)

        if ismethod(target_function):
            return classmethod(_wrapped_function)
        elif type(target_function) is property:
            return property(_wrapped_function)
        return _wrapped_function

    @staticmethod
    def wrap(target_object: Any, target_function_name: str) -> Callable:
        def _wrap(wrapper_function) -> Any:
            target_function = getattr(target_object, str(target_function_name))
            setattr(target_object, str(target_function_name),
                    Wrapper._wrap_helper(target_function, wrapper_function))
            return wrapper_function

        return _wrap


#####
# sliders and variables
slider_sets = [
    {
    # feminine frame
        15575175292544645782: 1.0,    # belly (low)
        11930680302218363414: 1.0,    # butt (high)
        7507470142880626878: 0.5,    # feet (low)
        5374208749069135862: 0.2,    # hips (high)
        3133421862343476390: 0.5,    # lower arms (high)
        8990366144061439592: 0.37,    # lower legs (high)
        14190157834369024263: 1.0,    # neck (low)
        8261922974690070905: 0.6,    # shoulder (low)
        2691083872543754775: 0.5,    # upper arms (high)
        7928916107912367106: 1.0,    # upper legs (high)
        14010151319568370160: 1.0    # waist (low)
    },
    {
    # feminine frame breast sliders
        10172784403806973628: 1.0,    # chestdepth (high)
        6248723735190925703: 1.0,    # chestlift (low)
        10160417097015316330: 1.0,    # chestsize (high)
    },
    {
    # masculine frame
        8990366144061439592: 0.01,
        16892734955963417493: 0.01,
        1305153429805576266: 0.217,
        12410017839419515581: 1.0,
        1701565032762897701: 0.783,
        712054970721619767: 0.04,
        10981293205619467162: 0.342,
        3153939009691209395: 0.124,
        1554888732433422503: 0.5,
        1670192638776885870: 0.56,
        5941347650567105741: 0.42,
        6468277340439150134: 0.033,
        12742648587447422229: 0.113
    },
    {
    # masculine frame breast sliders
        3999837669087888828: 1.0,
        10160417097015316330: 1.0
    }
]


def bh_set_attributes(facial_attributes: PersistenceBlobs_pb2.BlobSimFacialCustomizationData,
                      part_keys) -> bool:
    local_part_keys = part_keys.copy()
    did_set = False
    to_remove = []
    for i, b_mod in enumerate(facial_attributes.body_modifiers):
        if b_mod.key in local_part_keys:
            if not isclose(b_mod.amount, local_part_keys[b_mod.key], abs_tol=1e-6):
                did_set = True
                facial_attributes.body_modifiers[i].amount = local_part_keys[b_mod.key]
            local_part_keys.pop(b_mod.key)
        else:
            did_set = True
            to_remove.append(b_mod)
    if len(local_part_keys) > 0:
        did_set = True
        for k, v in local_part_keys.items():
            mod = facial_attributes.body_modifiers.add()
            mod.key = k
            mod.amount = v
    for b_mod in to_remove:
        facial_attributes.body_modifiers.remove(b_mod)
    return did_set


def bh_helper(sim_info: SimInfo) -> bool:
    if sim_info.species != Species.HUMAN or sim_info.age <= Age.CHILD:
        return False
    trait_manager = services.get_instance_manager(sims4.resources.Types.TRAIT)
    trait_feminine_frame = trait_manager.get(136878)
    trait_masculine_frame = trait_manager.get(136877)
    trait_breasts_on = trait_manager.get(136863)
    trait_breasts_off = trait_manager.get(136862)
    to_set = dict()
    if sim_info.has_trait(trait_feminine_frame):
        base_slider_set = 0
    elif sim_info.has_trait(trait_masculine_frame):
        base_slider_set = 2
    to_set.update(slider_sets[base_slider_set])
    if (sim_info.gender == Gender.MALE and sim_info.has_trait(trait_breasts_on)) or (
            sim_info.gender == Gender.FEMALE and not sim_info.has_trait(trait_breasts_off)):
        to_set.update(slider_sets[base_slider_set + 1])
    facial_attributes = PersistenceBlobs_pb2.BlobSimFacialCustomizationData()
    facial_attributes.ParseFromString(sim_info.facial_attributes)
    if bh_set_attributes(facial_attributes, to_set):
        sim_info.facial_attributes = facial_attributes.SerializeToString()
        sim_info.resend_facial_attributes()
        return True
    return False


#####
# bh injections
@Wrapper.wrap(SimSpawner, SimSpawner.spawn_sim.__name__)
def bH_on_spawned(original, cls, sim_info, *args, **kwargs) -> Any:
    result = original(sim_info, *args, **kwargs)
    if result:
        bh_helper(sim_info)
    return result


@Wrapper.wrap(OccultTracker, OccultTracker.switch_to_occult_type.__name__)
def bh_on_occulted(original, self, *args, **kwargs) -> Any:
    result = original(self, *args, **kwargs)
    bh_helper(self._sim_info)
    return result


@Wrapper.wrap(AgingMixin, AgingMixin.change_age.__name__)
def bh_on_aged(original, self, *args, **kwargs) -> Any:
    result = original(self, *args, **kwargs)
    bh_helper(self)
    return result
