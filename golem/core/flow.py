import importlib
import re
from typing import Iterable

from .templates import Templates


class Flow:
    def __init__(self, name, dialog, definition):
        self.name = name
        self.dialog = dialog
        self.states = {}
        self.current_state_name = 'root'
        self.intent = definition.get('intent') or name
        for state_name, state_definition in definition['states'].items():
            self.states[state_name] = State(name + '.' + state_name, dialog=dialog, definition=state_definition)

    def get_state(self, state_name):
        return self.states.get(state_name)

    def __str__(self):
        return self.name + ":flow"


class State:
    def __init__(self, name, dialog, definition):
        from .dialog_manager import DialogManager
        self.name = name  # type: str
        self.dialog = dialog  # type: DialogManager
        self.intent_transitions = definition.get('intent_transitions') or {}
        self.intent = definition.get('intent')
        self.init = self.create_action(definition.get('init'))
        self.accept = self.create_action(definition.get('accept'))

    def create_action(self, definition):
        if not definition:
            return None
        if callable(definition):
            return definition
        template = definition.get('template')
        params = definition.get('params') or None
        if hasattr(Templates, template):
            fn = getattr(Templates, template)
        else:
            raise ValueError('Template %s not found, create a static method Templates.%s' % (template))

        return fn(**params)

    def get_intent_transition(self, intent):
        for key, state_name in self.intent_transitions.items():
            if re.match(key, intent): return state_name
        return None

    def __str__(self):
        return self.name + ":state"

    def __repr__(self):
        return str(self)


def require_one_of(entities=[]):
    def decorator_wrapper(func):
        def func_wrapper(state):
            all_entities = entities + ['intent', '_state']
            if not state.dialog.context.has_any(all_entities, max_age=0):
                print('No required entities present, moving to default.root: {}'.format(all_entities))
                return None, 'default.root:accept'
            return func(state)

        return func_wrapper

    return decorator_wrapper


class NewState:
    def __init__(self, name: str, action, intent=None):
        """
        Construct a conversation state.
        :param name:    name of this state
        :param action:  function that will run when moving to this state
        :param intent
        """
        self.name = str(name)
        self.action = action
        self.intent = intent

    @staticmethod
    def load(definition: dict) -> tuple:
        name = definition['name']
        if 'action' in definition:
            action = definition['action']
            action = NewState.make_action(action)
        else:
            action = None  # FIXME nop or what
        intent = definition.get("intent")
        s = NewState(name=name, action=action, intent=intent)
        return name, s

    @staticmethod
    def make_action(action):
        if callable(action):
            # action already given as object, everything ok
            return action
        elif isinstance(action, str):
            # dynamically load the function
            try:
                module_name, fn_name = action.rsplit(".", maxsplit=1)
                module = importlib.import_module(module_name)
                fn = getattr(module, fn_name)
                return fn
            except Exception as e:
                raise ValueError("Action {} is undefined or malformed".format(action)) from e
        elif isinstance(action, dict):
            # load a static action, such as text or image
            return NewState.make_default_action(action)

        raise ValueError("Action class {} not supported".format(type(action)))

    @staticmethod
    def make_default_action(action_dict):
        # TODO
        return None

    def __str__(self):
        return "state:" + self.name


class NewFlow:
    def __init__(self, name: str, states=None, intent=None):
        """
        Construct a new flow instance.
        :param name:   name of this flow
        :param states: dict of states (optional)
        :param intent: accepted intents regex (optional)
        """
        self.name = str(name)
        self.states = states or {}
        self.intent = intent or self.name

    @staticmethod
    def load(name, data: dict):
        states = dict(NewState.load(s) for s in data["states"])
        intent = data.get("intent", name)
        return NewFlow(name=name, states=states, intent=intent)

    def __getitem__(self, state_name: str):
        return self.states[state_name]

    def get_state(self, state_name: str):
        return self.states.get(state_name)

    def add_state(self, state: NewState):
        if isinstance(state, NewState):
            self.states[state.name] = state
            return self
        raise ValueError("Argument must be an instance of State")

    def get_state_for_intent(self, intent) -> str or None:
        for name, state in self.states.items():
            if state.intent and re.match(state.intent, intent):
                return self.name + "." + name
        return None

    def matches_intent(self, intent) -> bool:
        return re.match(intent, self.intent) is not None

    def __str__(self):
        return "flow:" + self.name


def load_flows_from_definitions(data: dict):
    flows = {}
    for flow_name, flow_definition in data.items():
        flow = NewFlow.load(flow_name, flow_definition)
        flows[flow_name] = flow
    return flows
