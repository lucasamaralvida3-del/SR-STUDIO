from pathlib import Path

path = Path("src/srstudio/graphics2/qml/ImageInspector.qml")
text = path.read_text(encoding="utf-8")

old = '''    function activePage() {
        if (!scene.pages || !scene.pages.length)
            return null
        for (var i = 0; i < scene.pages.length; ++i)
            if (scene.pages[i].id === scene.active_page_id)
                return scene.pages[i]
        return scene.pages[0]
    }

    function selectedImage() {
        var page = activePage()
        if (!page || !scene.editor)
            return null
        var id = String(scene.editor.anchor_id || "")
        var node = id && page.nodes ? page.nodes[id] : null
        if (!node && scene.editor.selection && scene.editor.selection.length)
            node = page.nodes[String(scene.editor.selection[0])] || null
        if (!node && page.nodes) {
            for (var nodeId in page.nodes) {
                if (page.nodes[nodeId] && page.nodes[nodeId].selected) {
                    node = page.nodes[nodeId]
                    break
                }
            }
        }
        return node && (node.kind === "image" || node.kind === "background") ? node : null
    }
'''
new = '''    function activePage(sourceScene) {
        var currentScene = sourceScene || scene
        if (!currentScene.pages || !currentScene.pages.length)
            return null
        for (var i = 0; i < currentScene.pages.length; ++i)
            if (currentScene.pages[i].id === currentScene.active_page_id)
                return currentScene.pages[i]
        return currentScene.pages[0]
    }

    function selectedImage(sourceScene) {
        var currentScene = sourceScene || scene
        var page = activePage(currentScene)
        if (!page || !currentScene.editor)
            return null
        var id = String(currentScene.editor.anchor_id || "")
        var node = id && page.nodes ? page.nodes[id] : null
        if (!node && currentScene.editor.selection && currentScene.editor.selection.length)
            node = page.nodes[String(currentScene.editor.selection[0])] || null
        if (!node && page.nodes) {
            for (var nodeId in page.nodes) {
                if (page.nodes[nodeId] && page.nodes[nodeId].selected) {
                    node = page.nodes[nodeId]
                    break
                }
            }
        }
        return node && (node.kind === "image" || node.kind === "background") ? node : null
    }
'''
if text.count(old) != 1:
    raise RuntimeError("expected exactly one activePage/selectedImage block")
text = text.replace(old, new, 1)

old = '''            scene = JSON.parse(sceneBridge.sceneJson)
            var selected = selectedImage()
            imageNode = selected
'''
new = '''            var parsedScene = JSON.parse(sceneBridge.sceneJson)
            var selected = selectedImage(parsedScene)
            scene = parsedScene
            imageNode = selected
'''
if text.count(old) != 1:
    raise RuntimeError("expected exactly one refresh selection block")
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("QML fresh-payload selection fix applied")
