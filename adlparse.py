import attr
import copy
import re
import typing as tp
import xml.etree.ElementTree as ET
import warnings
from collections import defaultdict
from functools import partial, reduce

from util import BiMultiDict
from util import MapView, frozendict

_LOC = tp.Tuple[int, int]

@attr.s(slots=True, auto_attribs=True, frozen=True)
class _INSTANCE:
    name         : str            = attr.ib(cmp=True)
    type_        : str            = attr.ib(cmp=True)
    input_ports  : tp.Set[str]    = attr.ib(cmp=True, converter=frozenset)
    output_ports : tp.Set[str]    = attr.ib(cmp=True, converter=frozenset)
    args   : tp.Mapping[str, str] = attr.ib(cmp=True, converter=frozendict)

@attr.s(slots=True, auto_attribs=True, frozen=True)
class _MUX:
    name         : str            = attr.ib(cmp=True)
    input_ports  : tp.Set[str]    = attr.ib(cmp=True, converter=frozenset)
    output_ports : tp.Set[str]    = attr.ib(cmp=True, converter=frozenset)
    @property
    def output_port(self) -> str:
        assert len(self.output_ports) == 1
        for p in self.output_ports: return p

@attr.s(slots=True, auto_attribs=True, frozen=True)
class _PORT:
    name        : str = attr.ib(cmp=True)
    input_port  : str = attr.ib(cmp=True)
    output_port : str = attr.ib(cmp=True)
    operand     : str = attr.ib(cmp=True)
    @property
    def input_ports(self) -> tp.Set[str]:
        return frozenset({self.input_port})

    @property
    def output_ports(self) -> tp.Set[str]:
        return frozenset({self.output_port})


@attr.s(slots=True, auto_attribs=True, cmp=True, hash=True)
class _BLOCK:
    name         : str                                 = attr.ib(cmp=True)
    input_ports  : tp.Set[str]                         = attr.ib(cmp=True, converter=frozenset)
    output_ports : tp.Set[str]                         = attr.ib(cmp=True, converter=frozenset)
    instances    : tp.Dict[str, _INSTANCE]             = attr.ib(cmp=False, default=attr.Factory(dict))
    muxes        : tp.Dict[str, _MUX]                  = attr.ib(cmp=False, default=attr.Factory(dict))
    ports        : tp.Dict[str, _PORT]                 = attr.ib(cmp=False, default=attr.Factory(dict))
    ties         : tp.MutableMapping[str, tp.Set[str]] = attr.ib(cmp=False, default=attr.Factory(BiMultiDict))

    @property
    def insts_and_muxes(self) -> tp.ItemsView[str, tp.Union[_MUX, _PORT, _INSTANCE]]:
        yield from self.instances.items()
        yield from self.muxes.items()
        yield from self.ports.items()


_ADDRESS = tp.Tuple[_LOC, tp.Union[_MUX, _PORT, _INSTANCE], str] # ((row, col), instance, port)
_UNFLATTENED_TIE_MAP = tp.MutableMapping[tp.Tuple[_LOC, str], tp.Tuple[_LOC, str]]

@attr.s(slots=True, auto_attribs=True)
class _CGRA:
    rows    : int
    cols    : int
    blocks  : tp.Dict[_LOC, _BLOCK]                         = attr.ib(default=attr.Factory(dict))
    ties    : tp.MutableMapping[_ADDRESS, tp.Set[_ADDRESS]] = attr.ib(default=attr.Factory(BiMultiDict))


_INTERFACES = {
    'IO' : {
        'input_ports'  : {'in',},
        'output_ports' : {'out',},
    },
    'Register' : {
        'input_ports'  : {'in',},
        'output_ports' : {'out',},
    },
    'FuncUnit' : {
        'input_ports'  : {'in_a', 'in_b',},
        'output_ports' : {'out',},
    },
    'ConstUnit' : {
        'input_ports' : {},
        'output_ports' : {'out',},
    },
}

_OPERAND_MAP = {
    'IO' : {'in' : 0},
    'Register' : {'in' : 0},
    'FuncUnit' : {'in_a' : 0, 'in_b' : 1},
}

_DEFAULT_OP_MAP = {
    'IO' :  {'input', 'output',},
    'ConstUnit' : {'const',},
    'Register' : set(),
}



_HACK_SEP='-'

def _get_src(cgra : _CGRA,
        ties : _UNFLATTENED_TIE_MAP,
        loc : _LOC,
        src_path : str) -> _ADDRESS:

    #print(loc,  src_path)

    block = cgra.blocks[loc]
    src_name, src_port = src_path.split('.')
    if src_name == 'this':
        if src_port in block.output_ports:
            srcs = block.ties.I[src_path]
            assert len(srcs) == 1
            return _get_src(cgra, ties, loc, srcs[0])

        else:
            try:
                srcs = ties.I[loc, src_port]
            except KeyError:
                return None
            assert len(srcs) == 1
            outer_loc, outer_port = srcs[0]
            return _get_src(cgra, ties, outer_loc, f'this.{outer_port}')
    else:
        if src_name in block.instances:
            inst = block.instances[src_name]
        elif src_name in block.ports:
            inst = block.ports[src_name]
        else:
            inst = block.muxes[src_name]

        if src_port in inst.input_ports:
            try:
                srcs = block.ties.I[src_path]
            except KeyError:
                return None
            assert len(srcs) == 1
            return _get_src(cgra, ties, loc, srcs[0])
        else:
            assert src_port in inst.output_ports
            return (loc, inst, src_port)


def _get_dsts(cgra : _CGRA,
        ties : _UNFLATTENED_TIE_MAP,
        loc : _LOC,
        dst_path : str) -> tp.Set[_ADDRESS]:

    #print(loc,  dst_path)
    block = cgra.blocks[loc]
    dst_name, dst_port = dst_path.split('.')
    if dst_name == 'this':
        if dst_port in block.input_ports:
            return set.union(*(_get_dsts(cgra, ties, loc, x) for x in block.ties[dst_path]))
        else:
            assert dst_port in block.output_ports
            return set.union(*(_get_dsts(cgra, ties, lx, f'this.{x}') for lx, x in ties[loc, dst_port]))
    else:
        if dst_name in block.instances:
            inst = block.instances[dst_name]
        elif dst_name in block.ports:
            inst = block.ports[dst_name]
        else:
            inst = block.muxes[dst_name]

        if dst_port in inst.input_ports:
            return {(loc, inst, dst_port)}
        else:
            assert dst_port in inst.output_ports
            return set.union(*(_get_dsts(cgra, ties, loc, x) for x in block.ties[dst_path]))


def _verify_block(this_block : _BLOCK):
    for port in this_block.input_ports:
        assert port not in this_block.output_ports
    for port in this_block.output_ports:
        assert port not in this_block.input_ports

    for src in this_block.ties:
        inst, port = src.split('.')
        if inst == 'this':
            assert inst not in this_block.instances
            assert inst not in this_block.muxes
            assert inst not in this_block.ports
            assert port in this_block.input_ports, (this_block, port)
        elif inst in this_block.instances:
            assert inst not in this_block.muxes
            assert inst not in this_block.ports
            assert inst == this_block.instances[inst].name
            assert port in this_block.instances[inst].output_ports
        elif inst in this_block.ports:
            assert inst not in this_block.instances
            assert inst not in this_block.muxes
            assert port == this_block.ports[inst].output_port, (inst, port, this_block.ports[inst].output_port)
        else:
            assert inst in this_block.muxes, (inst, this_block.muxes.keys())
            assert inst == this_block.muxes[inst].name
            assert port in this_block.muxes[inst].output_ports

    for dst in this_block.ties.I:
        assert len(this_block.ties.I[dst]) == 1
        inst, port = dst.split('.')
        if inst == 'this':
            assert inst not in this_block.instances
            assert inst not in this_block.muxes
            assert inst not in this_block.ports
            assert port in this_block.output_ports, (this_block, port)
        elif inst in this_block.instances:
            assert inst not in this_block.muxes
            assert inst not in this_block.ports
            assert inst == this_block.instances[inst].name
            assert port in this_block.instances[inst].input_ports
        elif inst in this_block.ports:
            assert inst not in this_block.instances
            assert inst not in this_block.muxes
            assert port == this_block.ports[inst].input_port
            hack, dst_, dst_port = inst.split(_HACK_SEP)
            assert hack == 'PORT'
            assert dst_ in this_block.instances
            assert dst_port in this_block.instances[dst_].input_ports
        else:
            assert inst in this_block.muxes
            assert inst == this_block.muxes[inst].name
            assert port in this_block.muxes[inst].input_ports, (port, this_block.muxes[inst].input_ports)

    for inst_name, inst in this_block.insts_and_muxes:
        for port in inst.input_ports:
            if not f'{inst_name}.{port}' in this_block.ties.I:
                warnings.warn(f'disconnected instance port {inst_name}.{port} in {this_block.name}')
            assert port not in inst.output_ports
        for port in inst.output_ports:
            assert port not in inst.input_ports


def _verify_pre_flatten_cgra(cgra : _CGRA, ties : _UNFLATTENED_TIE_MAP):
    for loc, port in ties:
        if not loc in cgra.blocks:
            warnings.warn(f'input doest not exist @ {loc}')
            continue
        block = cgra.blocks[loc]
        assert isinstance(block, _BLOCK)
        assert port in block.output_ports

    for loc, port in ties.I:
        if not loc in cgra.blocks:
            warnings.warn(f'output does not exist block @ {loc}')
            continue
        block = cgra.blocks[loc]
        assert isinstance(block, _BLOCK)
        assert port in block.input_ports, (loc, port, block)
        assert len(ties.I[loc, port]) == 1, (loc, port, ties.I[loc, port])

    for loc, block in cgra.blocks.items():
        # _verify_block(block)
        assert 0 <= loc[0] < cgra.rows
        assert 0 <= loc[1] < cgra.cols
        for port in block.input_ports:
            if not (loc, port) in ties.I:
                warnings.warn(f'disconnected block input: {port} @ {loc}')

    for loc, block in cgra.blocks.items():
        for inst_name, inst in block.insts_and_muxes:
            for port in inst.input_ports:
                address = (loc, inst, port)
                path = f'{inst_name}.{port}'
                src_address = _get_src(cgra, ties, loc, path)
                if src_address is None:
                    continue
                src_loc, src_inst, src_port = src_address
                src_path = f'{src_inst.name}.{src_port}'
                dsts = _get_dsts(cgra, ties, src_loc, src_path)
                assert address in dsts
            for port in inst.output_ports:
                address = (loc, inst, port)
                path = f'{inst_name}.{port}'
                dsts = _get_dsts(cgra, ties, loc, path)

                for dst_loc, dst_inst, dst_port in dsts:
                    dst_path = f'{dst_inst.name}.{dst_port}'
                    src = _get_src(cgra, ties, dst_loc, dst_path)
                    assert address == src, f'\naddress: {address}\ndst_path: {dst_path}\nscr: {src}'


def _verify_post_flatten_cgra(cgra : _CGRA, ties : _UNFLATTENED_TIE_MAP):
    for loc, block in cgra.blocks.items():
        for inst_name, inst in block.insts_and_muxes:
            for port in inst.input_ports:
                address = (loc, inst, port)
                assert address in cgra.ties.I, address
                assert port is not None

            for port in inst.output_ports:
                # not strictly necessary but lets check this anyway
                address = (loc, inst, port)
                assert address in cgra.ties
                assert port is not None


def adlparse(file_name : str, *, rewrite_name=None) -> _CGRA:
    tree = ET.parse(file_name)
    root = tree.getroot()
    assert root.tag == 'cgra'

    blocks = dict()

    for module in root.findall('module'):

        name = module.attrib['name']
        input_ports  = [x.attrib['name'] for x in module.findall('input')]
        output_ports = [x.attrib['name'] for x in module.findall('output')]

        blocks[name] = this_block = _BLOCK(name, input_ports, output_ports)

        #gather instances
        for x in module.findall('inst'):
            iname = x.attrib['name']
            # assert name is free
            assert iname != 'this'
            assert iname != this_block.name
            assert iname not in this_block.instances
            assert iname not in this_block.ties
            assert iname not in this_block.ports

            itype = x.attrib['module']
            args = {}
            for k,v in x.attrib.items():
                if k in {'name', 'module'}:
                    continue
                if v.startswith('(') and v.endswith(')'):
                    raise ValueError("Unsupported feature module param")
                args[k] = v.split()
            if 'op' not in args:
                args['op'] = _DEFAULT_OP_MAP[itype]

            this_block.instances[iname] = inst = _INSTANCE(iname, itype, _INTERFACES[itype]['input_ports'], _INTERFACES[itype]['output_ports'], args)

        wires = set()
        #build wires
        for x in module.findall('wire'):
            wname = x.attrib['name']
            assert wname != 'this'
            assert wname != this_block.name
            assert wname not in this_block.instances
            assert wname not in this_block.ties
            assert iname not in this_block.ports
            assert wname not in wires
            #save them so they can be contracted later
            wires.add(wname)

        #build muxes
        muxes = dict()
        # muxes :: name : (real_name, port_dict)
        # port_dict :: src : port
        ctr = 0
        for x in module.findall('connection'):
            assert 'to' in x.attrib
            if 'from' in x.attrib:
                assert 'select-from' not in x.attrib
                continue

            assert 'select-from' in x.attrib
            assert 'from' not in x.attrib
            paths = x.attrib['select-from'].split()
            if len(paths) < 2:
                assert len(paths) == 1
                continue

            dst_paths = x.attrib['to'].split()
            assert len(dst_paths) >= 1

            port_dict = frozendict({p : str(i) for i,p in enumerate(paths)})

            for d_path in dst_paths:
                mname = f'mux_{ctr}'
                assert mname != 'this'
                assert mname != this_block.name
                assert mname not in this_block.instances
                assert mname not in this_block.muxes
                assert mname not in this_block.ties
                assert mname not in wires
                ctr += 1
                muxes[d_path] = (mname, port_dict)
                this_block.muxes[mname] = _MUX(mname, port_dict.values(), ('out',))


        #build ties
        for x in module.findall('connection'):
            dst_paths = x.attrib['to'].split()
            if 'from' in x.attrib:
                src_paths = x.attrib['from'].split()
            else:
                src_paths = x.attrib['select-from'].split()

            for src in src_paths:
                if src in muxes:
                    mname = muxes[src][0]
                    srcp = f'{mname}.{this_block.muxes[mname].output_port}'
                    assert not src.startswith('this.')
                else:
                    srcp = src
                for dst in dst_paths:
                    if dst in muxes:

                        mname, mdict = muxes[dst]
                        dstp = f'{mname}.{mdict[src]}'
                        dst_args = dst.split('.')
                        if len(dst_args) > 1:
                            dst_inst, dst_port = dst_args
                            if dst_inst == 'this':
                                this_block.ties[f'{mname}.{this_block.muxes[mname].output_port}'] = dst
                            elif dst_inst in this_block.instances:
                                pname = f'PORT{_HACK_SEP}{dst_inst}{_HACK_SEP}{dst_port}'
                                if pname not in this_block.ports:
                                    operand = _OPERAND_MAP[this_block.instances[dst_inst].type_][dst_port]
                                    this_block.ports[pname] = port = _PORT(pname, 'in', 'out', operand)
                                    iport = port.input_port
                                    oport = port.output_port
                                    this_block.ties[f'{pname}.{oport}'] = dst
                                    this_block.ties[f'{mname}.{this_block.muxes[mname].output_port}'] = f'{pname}.{iport}'
                                else:
                                    port = this_block.ports[pname]
                                    assert port.operand == _OPERAND_MAP[this_block.instances[dst_inst].type_][dst_port]
                                    assert f'{pname}.out' in this_block.ties
                                    assert dst in this_block.ties[f'{pname}.out']
                            else:
                                assert 0

                    else:
                        dst_inst, dst_port = dst.split('.')

                        if dst_inst in this_block.instances:
                            pname = f'PORT{_HACK_SEP}{dst_inst}{_HACK_SEP}{dst_port}'
                            assert pname not in this_block.ports
                            operand = _OPERAND_MAP[this_block.instances[dst_inst].type_][dst_port]
                            this_block.ports[pname] = port = _PORT(pname, 'in', 'out', operand)

                            iport = port.input_port
                            oport = port.output_port
                            this_block.ties[f'{pname}.{oport}'] = dst
                            dstp = f'{pname}.{iport}'
                        else:
                            dstp = dst

                    this_block.ties[srcp] = dstp

        #contract wires
        for w in wires:
            if w in this_block.ties:
                w_dsts = this_block.ties[w]
            else:
                assert w not in this_block.ties.I
                continue
            if w in this_block.ties.I:
                w_srcs = this_block.ties.I[w]
            else:
                continue

            assert len(w_srcs) == 1, (w, w_srcs)
            for src in w_srcs:
                for dst in w_dsts:
                    this_block.ties[src] = dst

            del this_block.ties[w]

        #assert stuff
        _verify_block(this_block)


    assert len(root.findall('architecture')) == 1
    arch = root.find('architecture')

    rows, cols = int(arch.attrib['row']), int(arch.attrib['col'])
    cgra = _CGRA(rows, cols)



    #((src_row, src_col), src_port) -> ((dst_row, dst_col), dst_port)
    ties = BiMultiDict()

    if len(arch.findall('mesh')) or len(arch.findall('diagonal')):
        def _is_edge(row, col): return (row in {0, rows-1}) or (col in {0, cols-1})
        def _is_corner(row, col): return (row in {0, rows-1}) and (col in {0, cols-1})
        def _row_in_range(row): return 0 <= row < rows
        def _col_in_range(col): return 0 <= col < cols
        #build a block for IO
        itype = 'IO'
        iname = itype.lower()
        assert itype not in blocks
        blocks[itype] = io_block = _BLOCK(itype, _INTERFACES[itype]['input_ports'], _INTERFACES[itype]['output_ports'])
        io_block.instances[iname] = inst = _INSTANCE(iname, itype, io_block.input_ports, io_block.output_ports, {'op' : {'input', 'output'}})
        for port in inst.input_ports:
            pname = f'PORT{_HACK_SEP}{iname}{_HACK_SEP}{port}'
            operand = _OPERAND_MAP[itype][port]
            io_block.ports[pname] = _PORT(pname, 'in', 'out', operand)

        for port in io_block.input_ports:
            pname = f'PORT{_HACK_SEP}{iname}{_HACK_SEP}{port}'
            assert pname in io_block.ports, (pname, io_block.ports)
            iport = io_block.ports[pname].input_port
            oport = io_block.ports[pname].output_port
            io_block.ties[f'this.{port}'] = f'{pname}.{iport}'
            io_block.ties[f'{pname}.{oport}'] = f'{iname}.{port}'

        for port in io_block.output_ports:
            io_block.ties[f'{iname}.{port}'] = f'this.{port}'

        _verify_block(io_block)

        if len(arch.findall('mesh')):
            assert len(arch.findall('mesh')) == 1
            assert int(arch.attrib['cgra-rows']) == rows - 2
            assert int(arch.attrib['cgra-cols']) == cols - 2
            assert len(arch.findall('diagonal')) == 0
            assert len(arch.findall('pattern')) == 0
            mesh = arch.find('mesh')

            assert mesh.attrib['io'] == "every-side-port"
            assert len(mesh.findall('interior')) == 1

            interior = mesh.find('interior')

            mesh_builders = [
                (-1,  0, mesh.attrib['out-north'][1:], mesh.attrib['in-south'][1:]),
                ( 0,  1, mesh.attrib['out-east'][1:] , mesh.attrib['in-west'][1:] ),
                ( 0, -1, mesh.attrib['out-west'][1:] , mesh.attrib['in-east'][1:] ),
                ( 1,  0, mesh.attrib['out-south'][1:], mesh.attrib['in-north'][1:]),
            ]

        else:
            assert len(arch.findall('diagonal')) == 1
            assert int(arch.attrib['cgra-rows']) == rows - 2
            assert int(arch.attrib['cgra-cols']) == cols - 2
            assert len(arch.findall('mesh')) == 0
            assert len(arch.findall('pattern')) == 0
            mesh = arch.find('diagonal')

            assert mesh.attrib['io'] == "every-side-port"
            assert len(mesh.findall('interior')) == 1

            interior = mesh.find('interior')

            mesh_builders = [
                (-1,  0, mesh.attrib['out-north'][1:]    , mesh.attrib['in-south'][1:]),
                ( 0,  1, mesh.attrib['out-east'][1:]     , mesh.attrib['in-west'][1:] ),
                ( 0, -1, mesh.attrib['out-west'][1:]     , mesh.attrib['in-east'][1:] ),
                ( 1,  0, mesh.attrib['out-south'][1:]    , mesh.attrib['in-north'][1:]),
                (-1,  1, mesh.attrib['out-northeast'][1:], mesh.attrib['in-southwest'][1:]),
                (-1, -1, mesh.attrib['out-northwest'][1:], mesh.attrib['in-southeast'][1:]),
                ( 1,  1, mesh.attrib['out-southeast'][1:], mesh.attrib['in-northwest'][1:]),
                ( 1, -1, mesh.attrib['out-southwest'][1:], mesh.attrib['in-northeast'][1:]),
            ]
        irow = int(interior.attrib.get('row', 1))
        icol = int(interior.attrib.get('col', 1))
        iblocks = [blocks[x.attrib['module']] for x in interior.findall('block')]

        assert irow * icol == len(iblocks)

        #build the blocks
        ridx = 0
        cidx = 0
        for r in range(rows):
            for c in range(cols):
                if _is_corner(r, c):
                    continue
                elif _is_edge(r, c):
                    cgra.blocks[r, c] = io_block
                else:
                    cgra.blocks[r, c] = iblocks[ridx * icol + cidx]

                if c not in {0, cols-1}:
                    cidx = (cidx + 1) % icol
            if r not in {0, rows-1}:
                ridx = (ridx + 1) % irow

        for row_offset, col_offset, _src_port, _dst_port in mesh_builders:
            for src_row in range(rows):
                dst_row = src_row + row_offset
                if not _row_in_range(dst_row):
                    continue
                for src_col in range(cols):
                    dst_col = src_col + col_offset

                    if not _col_in_range(dst_col):
                        continue


                    if _is_corner(src_row, src_col) or _is_corner(dst_row, dst_col):
                        continue

                    src_is_io = _is_edge(src_row, src_col)
                    dst_is_io = _is_edge(dst_row, dst_col)

                    if src_is_io and dst_is_io:
                        continue
                    elif dst_is_io and (row_offset != 0 and col_offset != 0):
                        #don't wire IOs diagonaly
                        continue

                    if src_is_io:
                        src_port = 'out'
                    else:
                        src_port = _src_port

                    if dst_is_io:
                        dst_port = 'in'
                    else:
                        dst_port = _dst_port

                    src = (src_row, src_col), src_port
                    dst = (dst_row, dst_col), dst_port
                    ties[src] = dst
    else:
        assert len(arch.findall('pattern')) > 0
        assert len(arch.findall('mesh')) == 0
        assert len(arch.findall('diagonal')) == 0
        def _make_range(r):
            l, h = r.split()
            return range(int(l), int(h)+1)

        connect_expr = re.compile(
                #(rel row-offset col-offset).port -> row-offset, col-offset, port
                r'\(rel\s+(-?\d+)\s+(-?\d+)\)\.([a-zA-Z]\w*)'
            )

        def _get_connect_info(s):
            m = re.fullmatch(connect_expr, s)
            assert m is not None, s
            return int(m.group(1)), int(m.group(2)), m.group(3)

        for pattern in arch.findall('pattern'):
            pblocks = [blocks[x.attrib['module']] for x in pattern.findall('block')]

            connect_rules = []
            for c in pattern.findall('connection'):
                assert 'from' in c.attrib
                assert 'to' in c.attrib
                src_info = _get_connect_info(c.attrib['from'])
                dst_info = _get_connect_info(c.attrib['to'])
                connect_rules.append((src_info, dst_info))

            row_range = _make_range(pattern.attrib['row-range'])
            col_range = _make_range(pattern.attrib['col-range'])

            if pblocks:
                prow = int(pattern.attrib.get('row', 1))
                pcol = int(pattern.attrib.get('col', 1))
                assert prow * pcol == len(pblocks)

                for ridx, row in enumerate(row_range):
                    for cidx, col in enumerate(col_range):
                        cgra.blocks[row, col] = pblocks[(ridx % prow) * pcol + (cidx % pcol)]

            for row in row_range:
                for col in col_range:
                    for (sro, sco, src_port), (dro, dco, dst_port) in connect_rules:
                        src = (row+sro, col+sco), src_port
                        dst = (row+dro, col+dco), dst_port
                        ties[src] = dst


    _verify_pre_flatten_cgra(cgra, ties)

    #flatten ties
    for loc, block in cgra.blocks.items():
        for inst_name, inst in block.insts_and_muxes:
            for port in inst.input_ports:
                address = (loc, inst, port)
                path = f'{inst_name}.{port}'
                src_address = _get_src(cgra, ties, loc, path)
                cgra.ties[src_address] = address

    _verify_post_flatten_cgra(cgra, ties)

    if rewrite_name is not None:
        rewrite(rewrite_name, cgra, ties, root)

    return cgra

def rewrite(file : str,
        cgra : _CGRA,
        ties : _UNFLATTENED_TIE_MAP,
        old_root : ET.Element):
    root = ET.Element('cgra')

    for module in old_root.findall('module'):
        root.append(module)

    arch = ET.SubElement(root, 'architecture', {
        'col' : f'{cgra.cols}',
        'row' : f'{cgra.rows}',
        })

    for loc, block in cgra.blocks.items():
        pattern = ET.SubElement(arch, 'pattern', {
            'row-range' : f'{loc[0]} {loc[0]}',
            'col-range' : f'{loc[1]} {loc[1]}',
            })
        ET.SubElement(pattern, 'block', {'module' : block.name})


    for ((src_row, src_col), src_port), ((dst_row, dst_col), dst_port) in ties.items():
        pattern = ET.SubElement(arch, 'pattern', {
            'row-range' : f'{dst_row} {dst_row}',
            'col-range' : f'{dst_col} {dst_col}',
            })
        ET.SubElement(pattern, 'connection', {
            'from' : f'(rel {src_row - dst_row} {src_col - dst_col}).{src_port}',
            'to'   : f'(rel 0 0).{dst_port}',
            })


    et = ET.ElementTree(root)
    et.write(file)
    adlparse(file)

