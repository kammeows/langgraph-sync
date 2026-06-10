import libcst as cst

class RenameTransformer(cst.CSTTransformer):
    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef):
        if original_node.name.value == "old_function":
            # Use the .with_changes() method to safely clone and modify an immutable node
            return updated_node.with_changes(name=cst.Name("new_function"))
        return updated_node

source = "def old_function(): pass # this is a function"
tree = cst.parse_module(source)

# Apply the transformer
modified_tree = tree.visit(RenameTransformer())
print(modified_tree.code)  # Output: def new_function(): pass