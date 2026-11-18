"""Parse a small familiar mathematical notation into the validated Analysis IR AST."""

import ast
from .document import require

#: Syntax accepted by the editor; Python is parsed but never executed.
BINARY = {ast.Add:"add",ast.Sub:"sub",ast.Mult:"mul",ast.Div:"div",ast.FloorDiv:"div"}
#: Comparison operators retain their exact mathematical direction.
COMPARISON = {ast.LtE:"le",ast.Lt:"lt",ast.Eq:"eq"}


def parse(source):
    """Convert an editor expression without accepting statements, attributes or executable code.

    @param source Natural arithmetic such as total_budget(c, interference) <= deadline.
    @return Structured expression for normal domain typing at mapping time.
    """
    require(isinstance(source,str) and 0<len(source)<=8000,"invalid_expression","请输入算术表达式。")
    try:
        # @var tree Python's parser supplies syntax only; no eval or user imports are used.
        tree = ast.parse(source,mode="eval").body
    except (SyntaxError,ValueError) as error:
        raise ValueError("表达式语法不完整："+str(error)) from None

    def convert(node):
        """Translate one explicitly supported syntactic constructor.

        @param node Parsed syntax node.
        @return Tagged IR tree.
        """
        if isinstance(node,ast.Name):
            return {"op":"var","name":node.id}
        if isinstance(node,ast.Constant) and type(node.value) is int:
            return {"op":"nat","value":node.value}
        if isinstance(node,ast.BinOp) and type(node.op) in BINARY:
            return {"op":BINARY[type(node.op)],"left":convert(node.left),"right":convert(node.right)}
        if isinstance(node,ast.Compare) and len(node.ops)==1 and type(node.ops[0]) in COMPARISON:
            return {"op":COMPARISON[type(node.ops[0])],"left":convert(node.left),"right":convert(node.comparators[0])}
        if isinstance(node,ast.BoolOp) and isinstance(node.op,ast.And):
            # @var result, value Left-associated conjunction, with no truth-value coercion.
            result = convert(node.values[0])
            for value in node.values[1:]:
                result = {"op":"and","left":result,"right":convert(value)}
            return result
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords:
            return {"op":"call","symbol":node.func.id,"args":[convert(arg) for arg in node.args]}
        require(False,"unsupported_expression","请使用变量、自然数、函数调用、+ - * /、<= < == 或 and；复杂命题可使用结构化表达式。")
    return {"expression":convert(tree)}
