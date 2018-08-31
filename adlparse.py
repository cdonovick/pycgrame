import attr
import copy
import re
import typing as tp
import xml.etree.ElementTree as ET
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
}

_OPERAND_MAP = {
    'IO' : {'in' : 0},
    'Register' : {'in' : 0},
    'FuncUnit' : {'in_a' : 0, 'in_b' : 1},
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
            srcs = ties.I[loc, src_port]
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
            srcs = block.ties.I[src_path]
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
            assert f'{inst_name}.{port}' in this_block.ties.I
            assert port not in inst.output_ports
        for port in inst.output_ports:
            assert port not in inst.input_ports


def _verify_pre_flatten_cgra(cgra : _CGRA, ties : _UNFLATTENED_TIE_MAP):
    for loc, port in ties:
        assert loc in cgra.blocks, loc
        assert isinstance(cgra.blocks[loc], _BLOCK), cgra.blocks[loc]
        assert port in cgra.blocks[loc].output_ports

    for loc, port in ties.I:
        assert loc in cgra.blocks, loc
        block = cgra.blocks[loc]
        assert isinstance(block, _BLOCK)
        assert port in block.input_ports, (loc, port, block)
        assert len(ties.I[loc, port]) == 1, (loc, port)

    for loc, block in cgra.blocks.items():
        _verify_block(block)
        assert 0 <= loc[0] < cgra.rows
        assert 0 <= loc[1] < cgra.cols
        for port in block.input_ports:
            assert (loc, port) in ties.I, (loc, port)

    for loc, block in cgra.blocks.items():
        for inst_name, inst in block.insts_and_muxes:
            for port in inst.input_ports:
                address = (loc, inst, port)
                path = f'{inst_name}.{port}'
                src_loc, src_inst, src_port = _get_src(cgra, ties, loc, path)
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


def adlparse(file_name : str) -> _CGRA:
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

            this_block.instances[iname] = inst = _INSTANCE(iname, itype, _INTERFACES[itype]['input_ports'], _INTERFACES[itype]['output_ports'], args)
            for port in inst.input_ports:
                pname = f'PORT{_HACK_SEP}{iname}{_HACK_SEP}{port}'
                operand = _OPERAND_MAP[itype][port]  
                this_block.ports[pname] = _PORT(pname, 'in', 'out', operand)


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
                    srcp = f'{muxes[src][0]}.out'
                    assert not src.startswith('this.')
                else:
                    srcp = src
                for dst in dst_paths:
                    if dst in muxes:
                        dst_name = f'{muxes[dst][0]}'
                        dstp = f'{dst_name}.{muxes[dst][1][src]}'
                        if dst.startswith('this.'):
                            this_block.ties[f'{dst_name}.out'] = dst
                    else:
                        dst_inst, dst_port = dst.split('.')

                        if dst_inst in this_block.instances:
                            pname = f'PORT{_HACK_SEP}{dst_inst}{_HACK_SEP}{dst_port}'
                            assert pname in this_block.ports
                            iport = this_block.ports[pname].input_port
                            oport = this_block.ports[pname].output_port
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

    
    assert len(root.findall('architecture')) == 1
    arch = root.find('architecture')

    assert len(arch.findall('mesh')) == 1
    mesh = arch.find('mesh')

    assert mesh.attrib['io'] == "every-side-port"
    assert len(mesh.findall('interior')) == 1

    interior = mesh.find('interior')
    
    rows, cols = int(arch.attrib['row']), int(arch.attrib['col'])
    assert int(arch.attrib['cgra-rows']) == rows - 2
    assert int(arch.attrib['cgra-cols']) == cols - 2
    

    cgra = _CGRA(rows, cols)

    irow = int(interior.attrib.get('row', 1))
    icol = int(interior.attrib.get('col', 1))
    iblocks = [blocks[x.attrib['module']] for x in interior.findall('block')]
    
    assert irow * icol == len(iblocks) 
    
    #build the blocks
    ridx = 0
    cidx = 0
    for r in range(rows):
        for c in range(cols):
            if (r in {0, rows-1}) ^ (c in {0, cols-1}):
                cgra.blocks[r,c] = io_block
            elif (r in {0, rows-1}) and (c in {0, cols-1}):
                pass 
            else:
                cgra.blocks[r,c] = iblocks[ridx * icol + cidx]

            if c not in {0, cols-1}:
                cidx = (cidx + 1) % icol
        if r not in {0, rows-1}:
            ridx = (ridx + 1) % irow


    #build unflattened ties
    ties = BiMultiDict()
    for row in range(rows):
        for col in range(cols):
            src_loc = row, col
            if src_loc not in cgra.blocks:
                continue
            for row_offset, col_offset, key, o_key in [
                    (-1,  0, 'out-north', 'in-south'),
                    ( 0, -1, 'out-east' , 'in-west' ),
                    ( 0,  1, 'out-west' , 'in-east' ),
                    ( 1,  0, 'out-south', 'in-north'),
                    ]:
                dst_loc = o_row, o_col = row + row_offset, col + col_offset 
                if dst_loc not in cgra.blocks:
                    continue
                if {row, o_row} <= {0, rows-1} or {col, o_col} <= {0, cols-1}:
                    #dont wire IOs to each other
                    continue

                src = src_loc,  mesh.attrib[key][1:]


                if (0 < o_row < rows-1) and (0 < o_col < cols-1):
                    dst = dst_loc,  mesh.attrib[o_key][1:]
                else:
                    dst = dst_loc, 'in' 

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

    return cgra
