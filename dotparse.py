import pydot

def dot2graph(file_name : str) -> (dict, set):
    g = pydot.graph_from_dot_file(file_name)
    assert len(g) == 1
    g = g[0]

    nodes = g.get_nodes()
    edges = g.get_edges()

    modules = dict()
    values = set()

    for node in nodes:
        inst_name = node.get_name()
        assert inst_name
        assert inst_name not in modules
        attrs = node.get_attributes()
        assert len(attrs) == 1
        assert 'opcode' in attrs
        modules[inst_name] = attrs['opcode']

    for edge in edges:
        src_name = edge.get_source()
        assert src_name in modules
        
        dst_name = edge.get_destination()
        assert dst_name in modules
                
        attrs = edge.get_attributes()
        assert len(attrs) == 1
        assert 'operand' in attrs
        
        dst_port = int(attrs['operand'])
        values.add((src_name, dst_name, dst_port))

    return modules, values


