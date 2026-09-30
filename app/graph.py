"""LangGraph workflow.

    START -> planner_agent
               |-- invalid request ----------------------------------------> output_agent
               '-- valid: fan-out (parallel)
                     flight_agent   hotel_agent   activity_agent      (each writes to the Blackboard)
                           '-------------+-------------'
                                         v   (fan-in: waits for all three)
                                    excel_sync                         (Blackboard -> Excel via MCP)
                                         v
                                    budget_agent                       (reads Excel via MCP)
                                         v
                                    output_agent -> END
"""
from langgraph.graph import END, START, StateGraph

from app.agents.activity_agent import activity_agent
from app.agents.budget_agent import budget_agent
from app.agents.flight_agent import flight_agent
from app.agents.hotel_agent import hotel_agent
from app.agents.output_agent import output_agent
from app.agents.planner_agent import SPECIALISTS, planner_agent, route_after_planner
from app.excel_sync import excel_sync
from app.state import TravelContext, TravelState


def build_graph():
    graph = StateGraph(TravelState, context_schema=TravelContext)

    graph.add_node("planner_agent", planner_agent)
    graph.add_node("flight_agent", flight_agent)
    graph.add_node("hotel_agent", hotel_agent)
    graph.add_node("activity_agent", activity_agent)
    graph.add_node("excel_sync", excel_sync)
    graph.add_node("budget_agent", budget_agent)
    graph.add_node("output_agent", output_agent)

    graph.add_edge(START, "planner_agent")
    graph.add_conditional_edges("planner_agent", route_after_planner, [*SPECIALISTS, "output_agent"])

    # A list of sources makes excel_sync wait until ALL three specialists finish.
    graph.add_edge(SPECIALISTS, "excel_sync")
    graph.add_edge("excel_sync", "budget_agent")
    graph.add_edge("budget_agent", "output_agent")
    graph.add_edge("output_agent", END)

    return graph.compile()


travel_graph = build_graph()
