import json
import os

BATCHES_PATH = "/Users/mac/prj/DW-SuperApps/.ua/intermediate/batches.json"
EXTRACT_PATH = "/Users/mac/prj/DW-SuperApps/.ua/tmp/ua-file-extract-results-19.json"
OUTPUT_PATH = "/Users/mac/prj/DW-SuperApps/.ua/intermediate/batch-19.json"

CATEGORY_TO_NODE_TYPE = {
    "docs": "document",
    "config": "config",
    "code": "file",
    "script": "file",
    "infra": "file",
}

def make_summary(file_info, metrics):
    path = file_info["path"]
    file_category = file_info["fileCategory"]
    sections = metrics.get("sectionCount", 0)
    basename = os.path.basename(path)

    if file_category == "config":
        if sections > 10:
            return f"YAML configuration file for {basename} with {sections} sections defining governance parameters."
        return f"YAML configuration file for {basename}."
    elif file_category == "docs":
        if sections > 10:
            return f"Documentation file {basename} with {sections} sections covering governance processes."
        return f"Documentation file {basename} with {sections} sections."
    elif file_category == "code":
        return f"Code file {basename}."
    elif file_category == "script":
        return f"Script file {basename}."
    else:
        return f"{file_category.capitalize()} file {basename}."

def make_tags(file_info):
    path = file_info["path"]
    file_category = file_info["fileCategory"]
    language = file_info["language"]
    tags = [file_category, language]

    if ".gwc/" in path:
        tags.append("gwc")
        if "/g0/" in path:
            tags.append("g0")
        elif "/g1/" in path:
            tags.append("g1")
        elif "/g2/" in path:
            tags.append("g2")
        elif "/g3/" in path:
            tags.append("g3")
        elif "/g4/" in path:
            tags.append("g4")
        elif "/g5/" in path:
            tags.append("g5")
        if "/tasks/" in path:
            tags.append("task")
        if "/scrums/" in path:
            tags.append("scrum")
        if "/decision/" in path:
            tags.append("decision")
        if "/preflight/" in path:
            tags.append("preflight")
        if "/intake/" in path:
            tags.append("intake")
        if "/brainstorming/" in path:
            tags.append("brainstorming")
        if "/execution/" in path:
            tags.append("execution")
        if "/delivery/" in path:
            tags.append("delivery")
        if "/merge/" in path:
            tags.append("merge")
        if "/deployment/" in path:
            tags.append("deployment")

    if file_category == "docs":
        tags.append("documentation")
    if file_category == "config":
        tags.append("configuration")

    return tags

def make_complexity(metrics):
    sections = metrics.get("sectionCount", 0)
    if sections > 15:
        return "complex"
    elif sections > 5:
        return "medium"
    return "simple"

def main():
    with open(BATCHES_PATH, "r") as f:
        batches_data = json.load(f)

    batch19 = None
    for batch in batches_data["batches"]:
        if batch["batchIndex"] == 19:
            batch19 = batch
            break

    if batch19 is None:
        raise ValueError("batchIndex 19 not found")

    with open(EXTRACT_PATH, "r") as f:
        extract_data = json.load(f)

    results_by_path = {}
    for result in extract_data["results"]:
        results_by_path[result["path"]] = result

    nodes = []
    edges = []

    for file_info in batch19["files"]:
        path = file_info["path"]
        file_category = file_info["fileCategory"]
        language = file_info["language"]
        node_type = CATEGORY_TO_NODE_TYPE.get(file_category, "file")
        node_id = f"{node_type}:{path}"
        basename = os.path.basename(path)

        extraction = results_by_path.get(path)
        metrics = extraction.get("metrics", {}) if extraction else {}

        nodes.append({
            "id": node_id,
            "type": node_type,
            "name": basename,
            "filePath": path,
            "summary": make_summary(file_info, metrics),
            "tags": make_tags(file_info),
            "complexity": make_complexity(metrics),
        })

    path_to_node_id = {}
    for n in nodes:
        path_to_node_id[n["filePath"]] = n["id"]

    for file_info in batch19["files"]:
        path = file_info["path"]
        file_category = file_info["fileCategory"]
        node_id = path_to_node_id.get(path)
        if node_id is None:
            continue

        import_targets = batch19["batchImportData"].get(path, [])
        for target in import_targets:
            if target in path_to_node_id:
                edges.append({
                    "source": node_id,
                    "target": path_to_node_id[target],
                    "type": "imports",
                    "direction": "forward",
                    "weight": 1.0,
                })

    for file_info in batch19["files"]:
        path = file_info["path"]
        file_category = file_info["fileCategory"]
        node_id = path_to_node_id.get(path)
        if node_id is None:
            continue

        parent_dir = os.path.dirname(path)
        if parent_dir and parent_dir != ".":
            for sibling_info in batch19["files"]:
                sibling_path = sibling_info["path"]
                if sibling_path == path:
                    continue
                sibling_dir = os.path.dirname(sibling_path)
                if sibling_dir == parent_dir:
                    sibling_node_id = path_to_node_id.get(sibling_path)
                    if sibling_node_id and sibling_node_id != node_id:
                        edges.append({
                            "source": node_id,
                            "target": sibling_node_id,
                            "type": "contains",
                            "direction": "forward",
                            "weight": 0.5,
                        })

    config_nodes = [n for n in nodes if n["type"] == "config"]
    doc_nodes = [n for n in nodes if n["type"] == "document"]

    for doc_node in doc_nodes:
        for config_node in config_nodes:
            doc_path = doc_node["filePath"]
            config_path = config_node["filePath"]
            doc_name = os.path.basename(doc_path).replace(".md", "")
            config_name = os.path.basename(config_path).replace(".yaml", "")
            if doc_name and config_name and doc_name in config_path or config_name in doc_path:
                edges.append({
                    "source": doc_node["id"],
                    "target": config_node["id"],
                    "type": "documents",
                    "direction": "forward",
                    "weight": 0.6,
                })

    for config_node in config_nodes:
        for other_config_node in config_nodes:
            if config_node["id"] == other_config_node["id"]:
                continue
            config_path = config_node["filePath"]
            other_path = other_config_node["filePath"]
            if "/g0/" in config_path and "/g1/" in other_path:
                edges.append({
                    "source": config_node["id"],
                    "target": other_config_node["id"],
                    "type": "configures",
                    "direction": "forward",
                    "weight": 0.7,
                })
            elif "/g1/" in config_path and "/g2/" in other_path:
                edges.append({
                    "source": config_node["id"],
                    "target": other_config_node["id"],
                    "type": "configures",
                    "direction": "forward",
                    "weight": 0.7,
                })
            elif "/g2/" in config_path and "/g3/" in other_path:
                edges.append({
                    "source": config_node["id"],
                    "target": other_config_node["id"],
                    "type": "configures",
                    "direction": "forward",
                    "weight": 0.7,
                })
            elif "/g3/" in config_path and "/g4/" in other_path:
                edges.append({
                    "source": config_node["id"],
                    "target": other_config_node["id"],
                    "type": "configures",
                    "direction": "forward",
                    "weight": 0.7,
                })
            elif "/g4/" in config_path and "/g5/" in other_path:
                edges.append({
                    "source": config_node["id"],
                    "target": other_config_node["id"],
                    "type": "configures",
                    "direction": "forward",
                    "weight": 0.7,
                })

    seen = set()
    unique_edges = []
    for edge in edges:
        key = (edge["source"], edge["target"], edge["type"])
        if key not in seen:
            seen.add(key)
            unique_edges.append(edge)

    node_count = len(nodes)
    edge_count = len(unique_edges)

    print(f"Nodes: {node_count}, Edges: {edge_count}")

    if node_count > 60 or edge_count > 120:
        parts = []
        mid = (node_count + 1) // 2
        for k in range(1, 3):
            part_nodes = nodes[(k - 1) * mid : k * mid] if k == 1 else nodes[(k - 1) * mid :]
            part_node_ids = {n["id"] for n in part_nodes}
            part_edges = [e for e in unique_edges if e["source"] in part_node_ids or e["target"] in part_node_ids]
            part = {
                "batchIndex": 19,
                "part": k,
                "nodes": part_nodes,
                "edges": part_edges,
            }
            parts.append(part)
            part_path = OUTPUT_PATH.replace("batch-19.json", f"batch-19-part-{k}.json")
            with open(part_path, "w") as f:
                json.dump(part, f, indent=2)
            print(f"Written {part_path} with {len(part_nodes)} nodes and {len(part_edges)} edges")
    else:
        output = {
            "batchIndex": 19,
            "nodes": nodes,
            "edges": unique_edges,
        }
        with open(OUTPUT_PATH, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Written {OUTPUT_PATH} with {node_count} nodes and {edge_count} edges")

if __name__ == "__main__":
    main()