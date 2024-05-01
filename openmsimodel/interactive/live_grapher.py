import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from gemd import MaterialTemplate, ProcessTemplate, MeasurementTemplate
from openmsimodel.entity.gemd.material import Material
from openmsimodel.entity.gemd.ingredient import Ingredient
from openmsimodel.entity.gemd.process import Process
from openmsimodel.entity.gemd.measurement import Measurement
from openmsimodel.structures.materials_sequence import MaterialsSequence
from openmsimodel.graph.open_graph import OpenGraph
import uuid


class liveGrapher(FileSystemEventHandler):
    mapping = {}
    output_folder = "./live_grapher_output"
    open_graphs = []

    def on_created(self, event):
        if event.is_directory:
            return
        filepath = event.src_path
        filename = os.path.basename(filepath)
        print(f"New file added: {filename}")
        file_name, file_extension = os.path.splitext(filepath)
        if file_extension in self.mapping.keys():
            to_be_visualized = define_run(self.mapping[file_extension])
        else:
            to_be_visualized = define_spec(
                file_extension, self.mapping, self.output_folder
            )
        open_graph = dump_graph(to_be_visualized, self.output_folder)
        self.open_graphs.append(open_graph)


def dump_graph(to_be_visualized, output):
    open_graph = OpenGraph(
        name=str(uuid.uuid4()),
        science_kit=None,
        source=to_be_visualized,
        output=output,
        which="run",
        dump_svg_and_dot=True,
    )
    G, relabeled_G, name_mapping = open_graph.build_graph(save=True)
    return open_graph


def define_run(mapping):
    for ingredient in mapping[2]:
        ingredient.generate_new_spec_run()
    for measurement in mapping[3]:
        measurement.generate_new_spec_run()
    materials_sequence = MaterialsSequence(
        name="None",
        science_kit=None,
        ingredients=mapping[2],
        process=mapping[1].generate_new_spec_run(),
        material=mapping[0].generate_new_spec_run(),
        measurements=mapping[3],
    )
    materials_sequence.link_within()
    return materials_sequence.assets


def define_spec(file_extension, mapping, output):
    measurement_name = input("Enter measurement name: ")
    measurement = Measurement(
        name=measurement_name, template=MeasurementTemplate(measurement_name)
    )
    material_name = input("Enter material name: ")
    material = Material(name=material_name, template=MaterialTemplate(material_name))
    process_name = input("Enter process name: ")
    process = Process(name=process_name, template=ProcessTemplate(process_name))
    ingredient_name = input("Enter ingredient name: ")
    ingredient = Ingredient(name=ingredient_name)

    mapping[file_extension] = [material, process, [ingredient], [measurement]]
    return define_run(mapping[file_extension])


# def define_spec(file_extension, mapping, output):
# template = {}
# for key, value in object_templates["properties"].items():
#     field_name = key
#     field_type = value.get("type")
#     field_description = value.get("description", "")

#     if field_type == "array":
#         template[field_name] = questionary.text(field_description).ask()
#     elif field_type == "string":
#         template[field_name] = questionary.text(field_description).ask()
#     # Add more conditions for other field types as needed...

# # Validate the input based on the schema
# validate(instance=template, schema=process_template_schema)

# # Use the populated template object
# print(template)


if __name__ == "__main__":
    folder_to_watch = "./live_grapher_input"
    event_handler = liveGrapher()
    observer = Observer()
    observer.schedule(event_handler, folder_to_watch, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()