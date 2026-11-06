"""The deterministic verifier: each tool's checks, and the task's, on contract instances."""

from contract import Task, Tool

from . import santa

# tool -> (verify_input(value), verify_output(input_value, output_value, workspace))
TOOLS = {
    Tool.GET_GROUP: (santa.verify_group_input, lambda given, made, workspace: santa.verify_group_output(given, made)),
    Tool.CHECK_ASSIGNMENT: (santa.verify_check_input, santa.verify_check_output),
    Tool.PIN_FEASIBILITY: (santa.verify_group_input, lambda given, made, workspace: santa.verify_pin_output(given, made)),
}
# task -> its output's check, verify_task(arguments, output, reference, workspace)
TASKS = {Task.MATCH_GIFTS: santa.verify_task}


def verify_input(tool, value):
    return TOOLS[Tool(tool)][0](value)


def verify_output(tool, input_value, output_value, workspace):
    return TOOLS[Tool(tool)][1](input_value, output_value, workspace)


def verify_task(task, arguments, output, reference, workspace):
    return TASKS[Task(task)](arguments, output, reference, workspace)
