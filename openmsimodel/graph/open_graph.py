import json
import networkx as nx
from collections import defaultdict
import shutil
import os
import matplotlib.pyplot as plt
import argparse
import pathlib

from gemd.util.impl import recursive_foreach
from gemd.json import GEMDJson

from openmsimodel.utilities.argument_parsing import OpenMSIModelParser
from openmsimodel.utilities.runnable import Runnable
from openmsimodel.utilities.tools import read_gemd_data


# TODO: add flag to open visualization tool?
# TODO: add file links and tags
class OpenGraph(Runnable):
    """this class provides modules to build and visualize a networkx or graphviz object from gemd objects.
    By taking folder path containing GEMD thin JSON files, it establishes the relationships
    between them by interpreting their uuids/links, and flexibly produces anything from
    a svg image with simple labels, to a dot products containing all the gemd assets,
    from attributes, file links or tags.
    """

    ARGUMENT_PARSER_TYPE = OpenMSIModelParser

    IPYNB_FILENAME = pathlib.Path(
        pathlib.Path(__file__).parent.resolve() / "open_graph_config/template.ipynb"
    )
    CONFIG_FILENAME = pathlib.Path(
        pathlib.Path(__file__).parent.resolve() / "open_graph_config/.config"
    )

    # instance attributes
    def __init__(self, dirpath):
        self.dirpath = pathlib.Path(dirpath)
        self.svg_path = None
        self.dot_path = None

    # instance method
    def build_graph(
        self, assets_to_add, add_separate_node, which, update=True, uuid_to_track="auto"
    ):
        """creates a NetworkX graph representation of the GEMD relationships by reading every object
        generated by the GEMDEncoder object, storing all of its links by uid, and forming directed relationships,
        such as ingredient->process, or process->material
        It then allows filtering the objects mapped (i.e., removing spec or runs,
        measurements or ingredients) and saves a NetworkX graph in "dot" as .png

        Args:
            which (bool): to plot a graph of specs, runs or templates
            add_separate_node (bool): bool to determine whether or not to add assets as attribute of related node, or as separate node
            assets_to_add (dict): dict to determine which of attributes, tags and/or file links to add to model
            update (bool, optional): bool to determinate updating instance variable svg_path and dot_path. Defaults to True.
            uuid_to_track (str, optional): _description_. Defaults to "auto".

        Returns:
            NetworkX Graph G: graph containing knowledge in question, with uuids as name
            NetworkX Graph G_relabeled: graph containing highlighted  knowledge in question, with individual names assigned to uuids
            dictionary name_mapping: mapping from uuid to name
        """

        print("-- Building {}s of {}".format(which, self.dirpath))
        G = nx.DiGraph()
        object_mapping = defaultdict()
        name_mapping = defaultdict()
        encoder = GEMDJson()
        nb_disregarded = 0

        gemd_objects = read_gemd_data(self.dirpath, encoder)

        if len(gemd_objects) == 0:
            return

        # adding objects to graph one by one
        for i, obj in enumerate(gemd_objects):
            if "raw_jsons" in obj:  # FIXME
                continue
            obj_data = obj
            if type(obj) == str:  # path
                fp = open(obj, "r")
                obj_data = json.load(fp)
            # if not (
            #     type(obj_data) == dict and "type" in obj_data.keys()
            # ):  # FIXME helps when reading a full mat history, or a list, in the same folder as others single jsons
            #     continue
            if type(obj_data) == list:
                continue
            obj_type = obj_data["type"]
            if (
                obj_type.startswith("parameter")
                or obj_type.startswith("condition")
                or obj_type.startswith("property")
            ):
                nb_disregarded += 1
                continue
            if not (uuid_to_track in obj_data["uids"].keys()):
                continue
            obj_uid = obj_data["uids"][uuid_to_track]
            obj_name = obj_data["name"]
            name_mapping[obj_uid] = "{},  {}".format(obj_name, obj_uid[:3])
            self.handle_gemd_obj(
                G,
                obj_uid,
                obj_data,
                obj_type,
                which,
                assets_to_add,
                add_separate_node,
            )
            if i % 1000 == 0:
                print("{} gemd objects processed...".format(i))

        # converting to grapviz
        relabeled_G = self.map_to_graphviz(G, name_mapping)

        # # plotting
        dot_path, svg_path = self.save_graph(
            self.dirpath, relabeled_G, name="{}_graph".format(which)
        )
        if update:
            self.update_paths(svg_path, dot_path)

        # info
        self.diagnostics(G, gemd_objects, nb_disregarded)

        return G, relabeled_G, name_mapping

    def handle_gemd_obj(
        self,
        G,
        uid,
        obj_data,
        obj_type,
        which,
        assets_to_add,
        add_separate_node,
    ):
        """method to handle the addition of a gemd object

        Args:
            G (NetworkX graph): graph
            uid (str): uid of current object
            obj_data (dict): data of current object
            obj_type (str): type of current object
            which (bool): to plot a graph of specs, runs or templates
            assets_to_add (dict): dict to determine which of attributes, tags and/or file links to add to model
            add_separate_node (bool):  bool to determine whether or not to add assets as attribute of related node, or as separate node
        """
        if obj_type.startswith("process"):
            if obj_type.endswith(which):
                G.add_node(uid, color="red")
                self.add_gemd_assets(
                    G,
                    uid,
                    obj_data,
                    "process",
                    which,
                    assets_to_add,
                    add_separate_node,
                )
        elif obj_type.startswith("ingredient"):  # TODO if node doesn't exist, create?
            if obj_type.endswith(which):
                G.add_node(uid, color="blue")
                process = obj_data["process"]["id"]
                G.add_edge(uid, process)
                # G.add_edge(process, uid)
                self.add_gemd_assets(
                    G,
                    uid,
                    obj_data,
                    "ingredient",
                    which,
                    assets_to_add,
                    add_separate_node,
                )
                if "material" in obj_data and obj_data["material"]:
                    material = obj_data["material"]["id"]
                    G.add_edge(material, uid)
        elif obj_type.startswith("material"):
            if obj_type.endswith(which):
                G.add_node(uid, color="green")
                self.add_gemd_assets(
                    G,
                    uid,
                    obj_data,
                    "material",
                    which,
                    assets_to_add,
                    add_separate_node,
                )
                # if "process" in obj_data and obj_data["process"]:
                if obj_data["process"] and obj_data["process"]:
                    process = obj_data["process"]["id"]
                    G.add_edge(process, uid)  # ?
        elif obj_type.startswith("measurement"):
            if obj_type.endswith(which):
                G.add_node(uid, color="purple")
                self.add_gemd_assets(
                    G,
                    uid,
                    obj_data,
                    "measurement",
                    which,
                    assets_to_add,
                    add_separate_node,
                )
                if "material" in obj_data and obj_data["material"]:
                    material = obj_data["material"]["id"]
                    G.add_edge(uid, material)

    def add_gemd_assets(
        self,
        G,
        uid,
        obj_data,
        object_class,
        which,
        assets_to_add,
        add_separate_node,
    ):
        if assets_to_add["add_attributes"] and "parameters" in obj_data:
            self.handle_gemd_value(G, uid, obj_data["parameters"], add_separate_node)
        if assets_to_add["add_attributes"] and "properties" in obj_data:
            self.handle_gemd_value(G, uid, obj_data["properties"], add_separate_node)
        if assets_to_add["add_attributes"] and "conditions" in obj_data:
            self.handle_gemd_value(G, uid, obj_data["conditions"], add_separate_node)
        if assets_to_add["add_file_links"] and "file_links" in obj_data:
            self.handle_gemd_value(G, uid, obj_data["file_links"], add_separate_node)
        if assets_to_add["add_tags"] and "tags" in obj_data:
            self.handle_gemd_value(G, uid, obj_data["tags"], add_separate_node)

    def handle_gemd_value(self, G, uid, assets, add_separate_node):
        # TODO: add pointing to templates?
        for att in assets:
            if type(att) in [str]:  # is a gemd tag
                if "::" in att:
                    self.add_to_graph(G, uid, att, "tags", add_separate_node=False)
            elif att["type"]:  # is a gemd object
                # reading gemd file links
                if att["type"] == "file_link":
                    self.add_to_graph(
                        G, uid, att["url"], "file_links", add_separate_node=False
                    )
                    continue
                # reading gemd attributes
                if att["type"] == "property_and_conditions":
                    value = att["property"]["value"]
                    att_name = att["property"]["name"]
                else:
                    value = att["value"]
                    att_name = att["name"]
                if value["type"] == "nominal_real":
                    node_name = "{}, {} {}".format(
                        att_name, value["nominal"], value["units"]
                    )
                elif value["type"] == "nominal_integer":
                    node_name = "{}, {}".format(att_name, value["nominal"])
                elif value["type"] == "uniform_real":
                    node_name = "{}, {}-{} {}".format(
                        att_name,
                        value["lower_bound"],
                        value["upper_bound"],
                        value["units"],
                    )
                elif (
                    value["type"] == "uniform_integer"
                ):  # FIXME same as above without units
                    node_name = "{}, {}-{}".format(
                        att_name,
                        value["lower_bound"],
                        value["upper_bound"],
                    )
                elif (
                    value["type"] == "empirical_formula"
                ):  # FIXME same as above without units
                    node_name = "{}, {}, {}".format(
                        att_name,
                        value["formula"],
                        value["type"],
                    )
                elif (
                    value["type"] == "normal_real"
                ):  # FIXME same as above without units
                    node_name = "{}, mean {}, std {}, {}, {}".format(
                        att_name,
                        value["mean"],
                        value["std"],
                        value["units"],
                        value["type"],
                    )
                elif value["type"] == "nominal_categorical":
                    node_name = "{}, {}".format(att_name, value["category"])
                elif value["type"] == "nominal_composition":
                    node_name = "{}, {}".format(att_name, value["quantities"])

                self.add_to_graph(G, uid, node_name, att_name, add_separate_node)

    def add_to_graph(self, G, uid, node_name, att_name, add_separate_node):
        if add_separate_node == True:  # add as a separate node
            G.add_node(node_name, shape="rectangle", color="orange")
            G.add_edge(uid, node_name)
        else:  # add as an attribute of the node
            if att_name in G.nodes[uid].keys():  # already exists, append to it
                count = len(G.nodes[uid][att_name])
                G.nodes[uid][att_name][count] = node_name
                return
            if att_name in ["file_links", "tags"]:
                G.nodes[uid][att_name] = {0: node_name}
            else:
                G.nodes[uid][att_name] = node_name

    def get_strongly_cc(self, G, node):
        """get strong connected component of node"""

        for cc in nx.strongly_connected_components(G):
            lst = []
            if node in cc:
                return cc
        else:
            return []

    def get_weakly_cc(self, G, node):
        """get weakly connected component of node"""
        for cc in nx.weakly_connected_components(G):
            if node in cc:
                return cc
        else:
            return []

    def diagnostics(self, G, gemd_objects, nb_disregarded):
        print("-- Analysis --")
        print("cycles in the graph: {}".format(list(nx.simple_cycles(G))))
        print(
            "nb of disregarded elements: {}/{}".format(
                nb_disregarded, len(gemd_objects)
            )
        )
        subgraphs = [G.subgraph(c).copy() for c in nx.strongly_connected_components(G)]
        print("number of connected components: {}".format(len(subgraphs)))
        print("nb of isolates: {}".format(nx.number_of_isolates(G)))

    @classmethod
    def launch_notebook(cls, dot_path):
        with open(cls.CONFIG_FILENAME, "w") as f:
            f.write(dot_path)
        # os.system(
        #     "jupyter nbconvert --execute --to notebook --inplace  {}".format(
        #         cls.IPYNB_FILENAME
        #     )
        # )
        # print(cls.IPYNB_FILENAME)
        # print(cls.IPYNB_FILENAME.parent)
        # exit()
        os.system(
            "jupyter notebook --notebook-dir={}".format(cls.IPYNB_FILENAME.parent)
        )
        return None

    def update_paths(self, svg_path, dot_path):
        self.svg_path = svg_path
        self.dot_path = dot_path

    @classmethod
    def map_to_graphviz(cls, G, name_mapping=None):
        """helper method to map NetworkX graph to Graphviz graph

        Args:
            G (_type_): _description_
            name_mapping (_type_, optional): _description_. Defaults to None.

        Returns:
            _type_: _description_
        """
        if name_mapping:
            G = nx.relabel_nodes(G, name_mapping)
        G = nx.nx_agraph.to_agraph(G)
        G.node_attr.update(nodesep=0.4)
        G.node_attr.update(ranksep=1)
        G.layout(prog="dot")
        return G

    @classmethod
    def slice_subgraph(cls, G, uuid, funcs, add_current=True):
        """applies paseed function(s) to graph object of interest with uuid=uuid.
        If elements are found to match the criteria, a subgraph containing all those elements is returned

        Args:
            G (NetworkX graph): knowledge graph in questoin
            uuid (str): uuid of current element of interest on which the functions are applied
            funcs (list): list of function(s) to apply to graph
            add_current (bool, optional): whether or not to add the current element of interest. Defaults to True.

        G (NetworkX graph): Graph to save
        """
        els = set()
        for func in funcs:
            els = els.union(func(G, uuid))
        if add_current:
            els.add(uuid)
        return G.subgraph(els)

    @classmethod
    def return_uuid(cls, identifier):
        """return the identifier of interest.

        Args:
            identifier (str): identifier of object of interest

        Returns:
            str: identifier
        """
        return identifier

    @classmethod
    def extract_subgraph(cls, G, identifier, func):
        """extract subgraph from graph knowledge, based on functions applied to element of interest to filter in additional desired elements.
        Examples includes neighbords, descendants, ancestors, etc.

        Args:
            G (NetworkX graph): Graph to save
            identifier (str): uuid or identifier of element of interest
            func (func): function to determine whether graph element should be added to subgraph or not

        Returns:
            NetworkX graph: subgraph filtered based on passed criteria
        """
        uuid = cls.return_uuid(identifier)
        return cls.slice_subgraph(G, uuid, func)

    @classmethod
    def save_graph(cls, dest, G, name):
        """class method to save Graphviz graph.

        Args:
            dest (Pathlib.Path): path where to save the graph
            G (Graphviz graph): Graph to save
            name (str): name of file to save graph to

        Returns:
            str: paths to, respectively, the dot and svg files
        """
        if os.path.isfile(dest):
            dest = dest.parent
        # svg file
        svg_path = os.path.join(dest, "{}.svg".format(name))
        # dot file
        dot_path = os.path.join(dest, "{}.dot".format(name))
        # writing svg file
        G.draw(svg_path)
        plt.close()
        # writing dot file
        with open(dot_path, "w") as f:
            f.write(str(G))
        print("-- Saved graph to {} and {}".format(dot_path, svg_path))
        return dot_path, svg_path

    @classmethod
    def get_argument_parser(cls, *args, **kwargs):
        parser = cls.ARGUMENT_PARSER_TYPE(*args, **kwargs)
        cl_args, cl_kwargs = cls.get_command_line_arguments()
        parser.add_arguments(*cl_args, **cl_kwargs)
        return parser

    @classmethod
    def get_command_line_arguments(cls):
        superargs, superkwargs = super().get_command_line_arguments()
        args = [
            *superargs,
            "dirpath",
            "which",
            "identifier",
            "launch_notebook",
            "add_attributes",
            "add_file_links",
            "add_tags",
            "add_separate_node",
            "a",
            "d",
            "uuid_to_track",
        ]
        kwargs = {**superkwargs}
        return args, kwargs

    @classmethod
    def run_from_command_line(cls, args=None):
        """
        Run a :class:`~OpenGraph` directly from the command line
        Calls :func:`~reconstruct` on a :class:`~OpenGraph` defined by
        command line (or given) arguments
        :param args: the list of arguments to send to the parser instead of getting them from sys.argv
        :type args: list, optional
        """
        parser = cls.get_argument_parser()
        args = parser.parse_args(args=args)
        viewer = cls(pathlib.Path(args.dirpath))
        assets_to_add = {
            "add_attributes": args.add_attributes,
            "add_file_links": args.add_file_links,
            "add_tags": args.add_tags,
        }
        G, relabeled_G, name_mapping = viewer.build_graph(
            assets_to_add=assets_to_add,
            add_separate_node=args.add_separate_node,
            which=args.which,
            uuid_to_track=args.uuid_to_track,
        )

        # reduces to elements with identifier and related nodes
        if args.identifier:
            functions = []
            if args.d:
                functions.append(nx.descendants)
            if args.a:
                functions.append(nx.ancestors)
            identifier_G = cls.extract_subgraph(G, args.identifier, func=functions)
            identifier_G = cls.map_to_graphviz(identifier_G, name_mapping)
            identifier_G_dot_path, _ = cls.save_graph(
                viewer.dirpath, identifier_G, "{}".format(args.identifier)
            )

        # launches interactive notebook
        if args.launch_notebook:
            if args.identifier:
                viewer.launch_notebook(identifier_G_dot_path)
            else:
                viewer.launch_notebook(viewer.dot_path)


def main(args=None):
    OpenGraph.run_from_command_line(args)


if __name__ == "__main__":
    main()