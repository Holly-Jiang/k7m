# -*- coding: utf-8 -*-

#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =============================================================================

"""
---------------> please fill out this section <---------------
v.2 == submitted after deadline just to solve two bugs which had a huge effect (very small changes to prev version are visible with diff)
 It was important to submit a script that generates correct circuits. Thus, we understand that it may not qualify for the competition, but we would greatly appreciate if it would qualify for being included in the official benchmark results.

Your Name : Alexandru Paler , Alwin Zulehner, Robert Wille

Your E-Mail : alexandru.paler@jku.at

Description of the algorithm : K7M

- How does the algorithm work?
In order to generate efficient heuristics and to compare their efficiency, we started analysing how an exact solution would look like, and where heuristics would fit into the exact model. The exact solution is a backtracking implemented on a stack. Each CNOT gate from the original circuit (should) increment(s) the levels of stack. The observation is that, it is necessary to place the CNOT on one of the edges of the coupling graph. Therefore, at each step there are 2|A| possible edges where the CNOT can be placed (the coupling graph is augmented with the reversed edges and has |A| edges). We recognised at least four places to include heuristics: 0) circuit preprocessing; 1) initial placement; 2) placing a CNOT on the coupling map; 3) grouping CNOTs (thus filling the stack faster); 4) methods for computing the necessary SWAPS between two stack levels (thus, between two CNOTs or two layers); 5) postprocessing of the circuit

The intention is to use a complete implementation of this algorithm (present version is not finished) to investigate the trade-offs between speed and efficiency. Currently, on the available test examples, using the very simple heuristics it achives on average 0.66x improvement compared to QISKit for a 33x speed-up. However, see correctness.

The current heuristics are:
1) initial placement is not configured. It is assumed that qubit_i is on coupling graph node i
[choose_initial_configuration]
2) a Floyd Warshall is executed on the coupling graph in order to determine all the pairs of shortest paths
lines 307-310
3) each CNOT qubit pair is moved to the coupling graph edge that is reached with a minimum distance
[heuristic_choose_coupling_edge_idx]

- Did you use any previously published schemes? Cite relevant papers.
No.

- What packages did you use in your code and for what part of the algorithm?
No package except the ones included by qiskit.

- How general is your approach? Does it work for arbitrary coupling layouts (qubit number)?
It should be general. See next note.

- Are there known situations when the algorithm fails?
Not aware in v2.
Previous comment was for v1: Yes. For the moment it passes the coupling map check, but it does not pass the correct_state_vector verification. The bug is assumed to be in the way indices between the coupling graph/coupling map/circuit are translated. However, this version of the implementation cannot be fixed on time, due to the deadline.

---------------> please fill out this section <---------------
"""

# Include any Python modules needed for your implementation here
import networkx as nx
import copy
import math
import sympy
import collections

from qiskit.dagcircuit import DAGCircuit
from qiskit.mapper import swap_mapper, direction_mapper, cx_cancellation, optimize_1q_gates, Coupling
# from qiskit import qasm, unroll

from gatesignatures import add_signatures_to_circuit, get_unrolled_qasm
from gatesimplifiers import paler_cx_cancellation, paler_simplify_1q

operation_costs = {"swap": 34, "rev_cnot": 4, "ok": 0}

def add_reverse_edges_and_weights(coupling, gatecosts):
    # get all edges from coupling
    edgs = copy.deepcopy(coupling.G.edges)
    for edg in edgs:
        # print(edg)
        coupling.G.remove_edge(*edg)

        # the direct edge gets a weight
        coupling.G.add_edge(edg[0], edg[1], weight=gatecosts["cx"])

        # the inverse edge
        # CNOT + four Hadamards for the reverse
        coupling.G.add_edge(edg[1], edg[0], weight=gatecosts["cx"] + 4*gatecosts["u2"])


def get_dag_nr_qubits(dag_circuit):
    """
    Get the number of qubits of the circuit
    Assume the circuit has a single qubit register called "q"
    """
    nrq = dag_circuit.qregs["q"]
    return nrq


def choose_initial_configuration(dag_circuit, coupling_object, random=False):
    """
        Returns an int-to-int map: logical qubit @ physical qubit map
        There is something similar in Coupling, but I am not using it
    """
    configuration = {}

    nrq = get_dag_nr_qubits(dag_circuit)
    import numpy
    x = numpy.random.permutation(nrq)
    for i in range(nrq):
        # configuration[i] = nrq - 1 - i # qubit i@i
        configuration[i] = i  # qubit i@i
        if random:
            configuration[i] = x[i]


#     use pagerank
#     import operator
#     pr1 = nx.pagerank(coupling_object["coupling"].G)
#     sorted_pr1 = sorted(pr1.items(), key=operator.itemgetter(1))
# #     print(sorted_pr1)
# #
#     qgraph = qubit_graph(dag_circuit, False)
#     pr2 = nx.pagerank(qgraph)
#     sorted_pr2 = sorted(pr2.items(), key=operator.itemgetter(1))
#     # print(sorted_pr2)
#     for i in range(len(pr1)):
#         configuration[sorted_pr2[i][0]] = sorted_pr1[i][0] - 1

    # import operator
    # qgraph = qubit_graph(dag_circuit, True)
    # g2 = nx.compose(qgraph, coupling_object["coupling"].G)
    # pos2 = nx.spectral_layout(g2)
    #
    # # import matplotlib.pyplot as plt
    # # print("pos2", pos2)
    # # nx.draw(g2, pos2)
    # # plt.show()
    #
    # coll2 = {}
    # for x in pos2:
    #     if x <= 0:
    #         coll2[-x] = pos2[x][1]
    # sorted_3 = sorted(coll2.items(), key=operator.itemgetter(1))
    # for i in range(len(sorted_3)):
    #     configuration[sorted_3[i][0]] = i

    return configuration


def get_position_of_qubits(qub1, qub2, configuration):
    return configuration[qub1], configuration[qub2]


def get_next_coupling_edge(backtracking_stack, coupling_edges_list):
    """
        Reads the stack and advances the index of the edge to send the qubits to
        Not used until now, because the backtracking step is not implemented
    """
    coupling_edge_index = backtracking_stack[-1][3]
    if coupling_edge_index + 1 < len(coupling_edges_list):
        return coupling_edges_list[coupling_edge_index + 1]
    #no edge remaining
    return None


def reconstruct_route(start, stop, coupling_pred):
    # route = []
    route = collections.deque()

    if coupling_pred[start][stop] is None:
        # can/should this happen?
        return []
    else:
        # route.append(stop)
        route.appendleft(stop)
        while start != stop:
            stop = coupling_pred[start][stop]
            # route.append(stop)
            route.appendleft(stop)

    # return list(reversed(route))
    return route

def get_coupling_node_idx(qubit, coupling, config_which_index):
    # return coupling.qubits[("q", config_which_index[qubit])]
    return coupling.qubits[("q", qubit)]


def is_pair_in_coupling_map(qubit1, qubit2, coupling_map):
    pair_pass = (qubit1 in coupling_map)
    if pair_pass:
        pair_pass &= qubit2 in coupling_map[qubit1]

    return pair_pass


def update_configuration(route, configuration, current_who_at_index):
    initial = []

    if len(route) == 0:
        return

    nr = copy.deepcopy(route)

    for i in range(0, len(nr)):
        initial.append(configuration[nr[i]])

    nr.append(nr[0])
    nr = nr[1:]

    for i in range(0, len(nr)):
        configuration[nr[i]] = initial[i]

    current_who_at_index.update({v: k for k, v in configuration.items()})


def compute_swap_chain_and_cost(route, coupling_map, no_circuit):
    """
        Returns a list of tuple of the form
        (g, ['q', i])? where g is "h" or "cx"
    """
    ret = []

    if len(route) == 0:
        return ret

    # print("route phys qubits", route)

    if not no_circuit:
        qub1 = route[0]
        for qub2 in route[1:]:
            qtmp = qub2
            is_error = False
            if not is_pair_in_coupling_map(qub1, qub2, coupling_map):
                qub1, qub2 = qub2, qub1 #swap variables
                if not is_pair_in_coupling_map(qub1, qub2, coupling_map):
                    print("NOT GOOD: Coupling not OK!", qub1, qub2)
                    is_error = True

            if not is_error:
                # print("swap", qub1, qub2)
                ret += compute_cnot_gate_list(qub1, qub2, False)
                ret += compute_cnot_gate_list(qub1, qub2, True)
                ret += compute_cnot_gate_list(qub1, qub2, False)

            qub1 = qtmp

    # print("-------")
    route_cost = (len(route) - 1) * operation_costs["swap"]

    return ret, route_cost


def compute_cnot_gate_list(qub1, qub2, inverse_cnot):
    ret = []

    if not inverse_cnot:
        ret.append({"name": "cx", "qargs": [("q", qub1), ("q", qub2)], "params": None})
    else:
        ret.append({"name": "u2", "qargs": [("q", qub1)], "params": [sympy.N(0), sympy.N(sympy.pi)]})
        ret.append({"name": "u2", "qargs": [("q", qub2)], "params": [sympy.N(0), sympy.N(sympy.pi)]})

        ret.append({"name": "cx", "qargs": [("q", qub1), ("q", qub2)], "params": None})

        ret.append({"name": "u2", "qargs": [("q", qub1)], "params": [sympy.N(0), sympy.N(sympy.pi)]})
        ret.append({"name": "u2", "qargs": [("q", qub2)], "params": [sympy.N(0), sympy.N(sympy.pi)]})

    return ret

def append_ops_to_dag(dag_circuit, op_list):

    for op in op_list:
        if paler_cx_cancellation(dag_circuit, op):
            if paler_simplify_1q(dag_circuit, op):
                dag_circuit.apply_operation_back(op["name"], op["qargs"], params=op["params"])

    return dag_circuit.node_counter


def qubit_graph(dag_circuit, negativeNodes=False):

    qgraph = nx.DiGraph()

    nodes_collection = nx.topological_sort(dag_circuit.multi_graph)

    edges_coll = {}
    for node in nodes_collection:
        gate = dag_circuit.multi_graph.nodes[node]
        if gate["name"] in ["cx", "CX"]:
            # found a cnot
            qub1, qub2 = get_cnot_qubits(gate)
            edg = (qub1, qub2)
            if negativeNodes:
                edg = (-qub1, -qub2)#used for spectral_layout
            if edg not in edges_coll:
                edges_coll[edg] = 0
            edges_coll[edg] += 1

    for edg in edges_coll:
        qgraph.add_edge(edg[0], edg[1], weight=edges_coll[edg])

    return qgraph

def compiler_function(dag_circuit, coupling_map=None, gate_costs=None):
    """
    Modify a DAGCircuit based on a gate cost function.

    Instructions:
        Your submission involves filling in the implementation
        of this function. The function takes as input a DAGCircuit
        object, which can be generated from a QASM file by using the
        function 'qasm_to_dag_circuit' from the included 
        'submission_evaluation.py' module. For more information
        on the DAGCircuit object see the or QISKit documentation
        (eg. 'help(DAGCircuit)').

    Args:
        dag_circuit (DAGCircuit): DAGCircuit object to be compiled.
        coupling_circuit (list): Coupling map for device topology.
                                 A coupling map of None corresponds an
                                 all-to-all connected topology.
        gate_costs (dict) : dictionary of gate names and costs.

    Returns:
        A modified DAGCircuit object that satisfies an input coupling_map
        and has as low a gate_cost as possible.
    """

    #update the costs
    operation_costs["rev_cnot"] = 4 * gate_costs["u2"]
    operation_costs["swap"] = 3 * gate_costs["cx"] + 4

    '''
        Prepare the Floyd Warshall graph and weight matrix
        Coupling related objects
    '''
    # How do you find out the number of qubits in the architecture if coupling_map is None?

    coupling_object = {"coupling": Coupling(coupling_map)}
    add_reverse_edges_and_weights(coupling_object["coupling"], gate_costs)
    coupling_object["coupling_pred"], coupling_object["coupling_dist"] = nx.floyd_warshall_predecessor_and_distance(coupling_object["coupling"].G, weight="weight")
    coupling_object["coupling_edges_list"] = [e for e in coupling_object["coupling"].G.edges()]

    '''
        Current logical qubit position on physical qubits
    '''
    current_positions = choose_initial_configuration(dag_circuit, coupling_object, False)
    current_who_at_index = {v: k for k, v in current_positions.items()}

    '''
        Start with an initial configuration
    '''

    # if get_dag_nr_qubits(dag_circuit) > 6:
    compiled_dag, backtracking_stack = find_solution(coupling_map, coupling_object, current_positions,
                                            current_who_at_index, dag_circuit, False)

    return compiled_dag
    # else:
    #     compiled_dag, backtracking_stack = find_solution(coupling_map, coupling_object, current_positions,
    #                                                      current_who_at_index, dag_circuit, True)

    '''
    Collect all configurations encountered
    '''
    collect_config = {}
    # analyse saved configurations
    for el in backtracking_stack:
        kkk = hash(frozenset(el[0].items()))
        if kkk not in collect_config:
            collect_config[kkk] = (0, el[0])
        collect_config[kkk] = (collect_config[kkk][0] + 1, collect_config[kkk][1])


    '''
        Find the configuration with the smallest cost
    '''
    min_cost = math.inf
    min_current_positions = "what is here?"
    for k in collect_config:
        # print(collect_config[k][0], ":", collect_config[k][1])
        current_who_at_index = {v: k for k, v in collect_config[k][1].items()}
        tmp_dag, backtracking_stack = find_solution(coupling_map, coupling_object, collect_config[k][1],
                                                         current_who_at_index, dag_circuit, True)

        # fourth element in the tuple is the cost
        tmp_solution_cost = sum(bs[3] for bs in backtracking_stack)

        # tmp_solution_cost, mapped_ok = check_solution_and_compute_cost(tmp_dag, coupling_map, gate_costs)
        if tmp_solution_cost <= min_cost:
            # compiled_dag = tmp_dag
            min_cost = tmp_solution_cost
            min_current_positions = k
        # mapped_ok = "did not check"
        # print(tmp_solution_cost, mapped_ok)

    '''
        The minimum cost configuration will be used
    '''
    current_who_at_index = {v: k for k, v in collect_config[min_current_positions][1].items()}
    compiled_dag, backtracking_stack = find_solution(coupling_map, coupling_object, collect_config[min_current_positions][1],
                                                current_who_at_index, dag_circuit, False)

    # compiled_dag = optimize_1q_gates(compiled_dag)
    # cx_cancellation(compiled_dag)
    #
    # print("--------- Check ------------")
    # tmp_solution_cost, mapped_ok = check_solution_and_compute_cost(compiled_dag, coupling_map, gate_costs)
    # print(tmp_solution_cost, mapped_ok)
    # if mapped_ok:
    #     print("Seems OK")

    return compiled_dag


def save_first_swaps(coupling_map, coupling_object, current_positions, current_who_at_index, dag_circuit):
    # print(coupling_map)
    nodes_collection = nx.topological_sort(dag_circuit.multi_graph)
    # get first set of disjunct cnots
    fcnots = first_set_of_disjunct_cnots(nodes_collection, dag_circuit.multi_graph, get_dag_nr_qubits(dag_circuit))
    # saved = 0
    for cnot in fcnots:
        op = translate_op_to_coupling_map(cnot, current_positions)
        qub1, qub2 = get_cnot_qubits(op)

        qubit_node_index1 = get_coupling_node_idx(qub1, coupling_object["coupling"], current_positions)
        qubit_node_index2 = get_coupling_node_idx(qub2, coupling_object["coupling"], current_positions)

        coupling_edge_idx = heuristic_choose_coupling_edge_idx(qubit_node_index1,
                                                               qubit_node_index2,
                                                               coupling_object)

        edge_node_index1 = coupling_object["coupling_edges_list"][coupling_edge_idx][0]
        edge_node_index2 = coupling_object["coupling_edges_list"][coupling_edge_idx][1]

        if qubit_node_index1 != edge_node_index1:
            move_qubit_from_to(qubit_node_index1, edge_node_index1,
                               coupling_map, coupling_object, current_positions,
                               current_who_at_index)

        if qubit_node_index2 != edge_node_index2:
            move_qubit_from_to(qubit_node_index2, edge_node_index2,
                               coupling_map, coupling_object, current_positions,
                               current_who_at_index)


def find_solution(coupling_map, coupling_object, current_positions, current_who_at_index,
                  dag_circuit, no_circuit):

    '''

    :param coupling_map:
    :param coupling_object:
    :param current_positions:
    :param current_who_at_index:
    :param dag_circuit: input dag circuit
    :param no_circuit:
    :return:
    '''

    save_first_swaps(coupling_map, coupling_object, current_positions, current_who_at_index, dag_circuit)

    # Simulate a stack
    backtracking_stack = []

    '''
        Initialise the stack and the compiled solution
    '''
    dag_circuit = add_signatures_to_circuit(dag_circuit)
    compiled_dag = None
    if not no_circuit:
        compiled_dag = clone_dag_without_gates(dag_circuit)
    else:
        compiled_dag = dag_circuit

    coupling_edge_idx = 0
    # last_gate_idx = compiled_dag.node_counter

    #make a list in order to allow forward iteration
    nodes_collection = list(nx.topological_sort(dag_circuit.multi_graph))

    for gate in nodes_collection:
        op_orig = dag_circuit.multi_graph.node[gate]
        if op_orig["type"] not in ["op"]:
            continue

        # print(op_orig)

        op = translate_op_to_coupling_map(op_orig, current_positions)

        if op["name"] not in ["cx", "CX"]:
            # print(op)
            '''
                A place to include a heuristic
            '''
            if not no_circuit:
                if op["name"] in ["u1", "u2", "u3"]:
                    append_ops_to_dag(compiled_dag, [op])
                else:
                    compiled_dag.apply_operation_back(op["name"], op["qargs"], op["cargs"], op["params"], op["condition"])
        else:
            '''
                Found a CNOT:
                Check that the qubits are on an edge
            '''
            qub1, qub2 = get_cnot_qubits(op)
            gates_to_insert = []

            # How much does a movement cost?
            additional_cost = 0

            if is_pair_in_coupling_map(qub1, qub2, coupling_map):
                # can be directly implemented
                gates_to_insert += compute_cnot_gate_list(qub1, qub2, False)
                additional_cost = operation_costs["ok"]
                # print("CNOT!!!", qub1, qub2, "from", get_cnot_qubits(op_orig))

            elif is_pair_in_coupling_map(qub2, qub1, coupling_map):
                # needs a reversed cnot
                gates_to_insert += compute_cnot_gate_list(qub2, qub1, True)
                additional_cost = operation_costs["rev_cnot"]
                # print("CNOT!!!", qub2, qub1, "from", get_cnot_qubits(op_orig))

            else:
                # print("do not add this", qub1, qub2)
                '''
                    qub 1 and qub2 are not a coupling_map edge
                    Compute a solution
                '''

                qubit_node_index1 = get_coupling_node_idx(qub1, coupling_object["coupling"], current_positions)
                qubit_node_index2 = get_coupling_node_idx(qub2, coupling_object["coupling"], current_positions)



                #get the next cnots and check use their coordinates to find the next edge
                next_nodes = []
                ni_index = nodes_collection.index(gate)
                #use 3 cnots
                for ni in range(6):
                    ni_index -= 1
                    if ni_index == -1:  # len(nodes_collection):
                        break

                    ni_id = nodes_collection[ni_index]
                    ni_op = dag_circuit.multi_graph.node[ni_id]
                    while ni_op["name"] not in ["cx", "CX"]:
                        ni_index -= 1
                        if ni_index == 0:#len(nodes_collection):
                            break
                        ni_id = nodes_collection[ni_index]
                        ni_op = dag_circuit.multi_graph.node[ni_id]

                    if ni_index == 0:#len(nodes_collection):
                        break

                    t_ni_op = translate_op_to_coupling_map(ni_op, current_positions)

                    ni_q1, ni_q2 = get_cnot_qubits(t_ni_op)
                    ni_q1_i = get_coupling_node_idx(ni_q1, coupling_object["coupling"], current_positions)
                    ni_q2_i = get_coupling_node_idx(ni_q2, coupling_object["coupling"], current_positions)
                    if ni_q1_i not in next_nodes and ni_q1_i not in [qubit_node_index1, qubit_node_index2]:
                        next_nodes.append(ni_q1_i)
                    if ni_q2_i not in next_nodes and ni_q2_i not in [qubit_node_index1, qubit_node_index2]:
                        next_nodes.append(ni_q2_i)

                # Compute the edgee index where the qubits could be moved
                coupling_edge_idx = heuristic_choose_coupling_edge_idx(qubit_node_index1,
                                                                       qubit_node_index2,
                                                                       coupling_object,
                                                                       next_nodes)

                #Determine the indices of the edge nodes where the qubits will be moved
                edge_node_index1 = coupling_object["coupling_edges_list"][coupling_edge_idx][0]
                edge_node_index2 = coupling_object["coupling_edges_list"][coupling_edge_idx][1]

                if qubit_node_index1 == edge_node_index2 and qubit_node_index2 == edge_node_index1:
                    # the qubits sit on opposite positions than expected
                    # do not compute routes
                    # but make an inverse cnot
                    if not no_circuit:
                        gates_to_insert += compute_cnot_gate_list(qubit_node_index2, qubit_node_index1, True)

                else:
                    if qubit_node_index1 != edge_node_index1:
                        # move the first qubit to the first edge node
                        route1, route1q = move_qubit_from_to(qubit_node_index1, edge_node_index1,
                                                                         coupling_map, coupling_object,
                                                                         current_positions,
                                                                         current_who_at_index)

                        # a circuit is not generated, do not place gates
                        ret_gates_to_insert, part_cost = compute_swap_chain_and_cost(route1q, coupling_map, no_circuit)
                        additional_cost += part_cost
                        if not no_circuit:
                            gates_to_insert += ret_gates_to_insert

                        '''
                            Update: the previous swaps may have moved this qubit around
                        '''
                        op = translate_op_to_coupling_map(op_orig, current_positions)
                        qub1, qub2 = get_cnot_qubits(op)
                        qubit_node_index2 = get_coupling_node_idx(qub2, coupling_object["coupling"], current_positions)

                    if qubit_node_index2 != edge_node_index2:
                        #move the second qubit to the second edge node
                        route2, route2q = move_qubit_from_to(qubit_node_index2, edge_node_index2,
                                                                         coupling_map, coupling_object,
                                                                         current_positions,
                                                                         current_who_at_index)
                        # a circuit is not generated, do not place gates
                        ret_gates_to_insert, part_cost = compute_swap_chain_and_cost(route2q, coupling_map, no_circuit)
                        additional_cost += part_cost
                        if not no_circuit:
                            gates_to_insert += ret_gates_to_insert

                        '''
                            Update: the previous swaps may have moved qub1 backwards
                        '''
                        if edge_node_index1 in route2:
                            # qubit_node_index1 = get_coupling_node_idx(qub1, coupling, current_positions)

                            qubit_node_index1 = route2[route2.index(edge_node_index1) - 1]

                            # this if-statement seems useless
                            if qubit_node_index1 != edge_node_index1:
                                route1, route1q = move_qubit_from_to(qubit_node_index1, edge_node_index1,
                                                                                 coupling_map, coupling_object,
                                                                                 current_positions,
                                                                                 current_who_at_index)

                                ret_gates_to_insert, part_cost = compute_swap_chain_and_cost(route1q, coupling_map, no_circuit)
                                additional_cost += part_cost
                                if not no_circuit:
                                    gates_to_insert += ret_gates_to_insert

                '''
                    It should be possible to implement the CNOT now
                '''
                # retranslate
                op2 = translate_op_to_coupling_map(op_orig, current_positions)
                qub1, qub2 = get_cnot_qubits(op2)

                if is_pair_in_coupling_map(qub1, qub2, coupling_map):
                    if not no_circuit:
                        gates_to_insert += compute_cnot_gate_list(qub1, qub2, False)
                    additional_cost += operation_costs["ok"]
                    # print("CNOT!!!", qub1, qub2, "from", get_cnot_qubits(op_orig))
                elif is_pair_in_coupling_map(qub2, qub1, coupling_map):
                    if not no_circuit:
                        gates_to_insert += compute_cnot_gate_list(qub2, qub1, True)
                    additional_cost += operation_costs["rev_cnot"]
                    # print("CNOT!!!", qub2, qub1, "from", get_cnot_qubits(op_orig))

            if not no_circuit:
                append_ops_to_dag(compiled_dag, gates_to_insert)

            # the others are not deep copied
            x = copy.deepcopy(current_positions)
            backtracking_stack.append((x, gate, coupling_edge_idx, additional_cost))

    return compiled_dag, backtracking_stack


def first_set_of_disjunct_cnots(nodes_collection, graph, maxqubits):
    used_qubits = []
    return_cnots = []

    for node in nodes_collection:
        gate = graph.nodes[node]
        if gate["name"] in ["cx", "CX"]:
            #found a cnot

            qub1, qub2 = get_cnot_qubits(gate)
            if qub1 not in used_qubits and qub2 not in used_qubits:
                used_qubits.append(qub1)
                used_qubits.append(qub2)

                return_cnots.append(gate)

        if len(used_qubits) == maxqubits:
            break

    return return_cnots

def move_qubit_from_to(qubit_node_index1, edge_node_index1, coupling_map, coupling_object, current_positions, current_who_at_index):

    '''
        Move the first qubit to the first edge position
    '''
    route1 = reconstruct_route(qubit_node_index1, edge_node_index1, coupling_object["coupling_pred"])
    route1q = [coupling_object["coupling"].index_to_qubit[r][1] for r in route1]

    '''
        Update the maps
    '''
    route1log = [current_who_at_index[x] for x in route1q]
    update_configuration(route1log, current_positions, current_who_at_index)
    # debug_configuration(current_positions)

    return route1, route1q


def heuristic_choose_coupling_edge_idx(qub1_to_index, qub2_to_index, coupling_object, next_nodes=[]):
    """
        Heuristic: which coupling edge generates the smallest cost given qub1 and qub2 positions
        Returns: the total cost of moving qub1 and qub2 and interacting them
    """
    # to debug
    # return 0

    ret_idx = -1

    min_cost = math.inf
    idx = -1

    for edge in coupling_object["coupling_edges_list"]:
        idx += 1
        edge1 = edge[0]
        edge2 = edge[1]

        cost1 = coupling_object["coupling_dist"][qub1_to_index][edge1]
        cost2 = coupling_object["coupling_dist"][qub2_to_index][edge2]
        # do not consider interaction cost?
        tmp_cost = cost1 + cost2# + coupling_object["coupling_dist"][qub1_to_index][qub2_to_index]

        f_idx = len(next_nodes)
        for node in next_nodes:
            tmp_cost += 0.05 * f_idx * coupling_object["coupling_dist"][node][edge1]
            tmp_cost += 0.05 * f_idx * coupling_object["coupling_dist"][node][edge2]
            f_idx -= 1

        if coupling_object["coupling_dist"][edge1][edge2] == 14:
            tmp_cost *= 1.1

        if tmp_cost <= min_cost:
            min_cost = tmp_cost
            ret_idx = idx

    # print(min_cost)

    return ret_idx


def translate_op_to_coupling_map(op, current_positions):
    '''
        Translate qargs and cargs depending on the position of the logical qubit
    '''

    retop = {}
    retop["name"] = op["name"]
    retop["type"] = op["type"]
    # TODO: deepcopy needed?
    retop["params"] = copy.deepcopy(op["params"])
    retop["condition"] = copy.deepcopy(op["condition"])

    retop["qargs"] = []
    for qa in op["qargs"]:
        x = current_positions[qa[1]]
        retop["qargs"].append(("q", x))

    # retop["cargs"] = []
    # for ca in op["cargs"]:
    #     x = current_positions[ca[1]]
    #     # if op["name"] in ["measure"]:
    #     #     x = ca[1]
    #     retop["cargs"].append(("c", x))

    retop["cargs"] = copy.deepcopy(op["cargs"])

    return retop


def clone_dag_without_gates(dag_circuit):
    compiled_dag = DAGCircuit()
    compiled_dag.basis = copy.deepcopy(dag_circuit.basis)
    compiled_dag.gates = copy.deepcopy(dag_circuit.gates)
    compiled_dag.add_qreg("q", get_dag_nr_qubits(dag_circuit))
    compiled_dag.add_creg("c", get_dag_nr_qubits(dag_circuit))
    return compiled_dag


def check_solution_and_compute_cost(dag_circuit, coupling_map, gate_costs):
    coupling_map_passes = True
    cost = 0

    #get nodes after topological sort
    nodescollection = nx.topological_sort(dag_circuit.multi_graph)
    for gate in nodescollection:
        op = dag_circuit.multi_graph.node[gate]

        # print(op)

        if op["name"] not in gate_costs:
            continue

        cost += gate_costs.get(op["name"])  # compute cost
        if op["name"] in ["cx", "CX"] \
                and coupling_map is not None:  # check coupling map

            qubit1, qubit2 = get_cnot_qubits(op)

            pair_pass = is_pair_in_coupling_map(qubit1, qubit2, coupling_map)

            if not pair_pass:
                print("here", qubit1, qubit2)

            coupling_map_passes &= pair_pass

    return cost, coupling_map_passes


def get_cnot_qubits(op):
    qubit1 = op["qargs"][0][1]

    qubit2 = -1
    if len(op["qargs"]) == 2:
        qubit2 = op["qargs"][1][1]

    return qubit1, qubit2


def debug_configuration(current_positions):
    print("-------------------")
    for i in range(0, len(current_positions)):
        print("q", i, "@", current_positions[i])

