import QtQuick

Item {
    id: root

    property url sourceUrl: ""
    property string fit: "contain"
    property real imageZoom: 1.0
    property real focusX: 0.5
    property real focusY: 0.5
    property bool flipX: false
    property bool flipY: false
    property bool asynchronous: true
    property bool cache: true
    property bool mipmap: true
    property bool smooth: true

    readonly property int status: sourceImage.status
    readonly property real naturalWidth: Math.max(1, Number(sourceImage.implicitWidth || 1))
    readonly property real naturalHeight: Math.max(1, Number(sourceImage.implicitHeight || 1))
    readonly property bool cropMode: fit === "cover" || imageZoom > 1.0001
    readonly property real baseScale: fit === "fill"
        ? 1.0
        : (cropMode
            ? Math.max(width / naturalWidth, height / naturalHeight)
            : Math.min(width / naturalWidth, height / naturalHeight))
    readonly property real scaleValue: fit === "fill" ? 1.0 : baseScale * (cropMode ? Math.max(0.05, imageZoom) : 1.0)
    // O renderer espelha a imagem-fonte antes de aplicar o foco. Como o QML
    // espelha o item depois do posicionamento, o foco precisa ser invertido no
    // eixo correspondente para produzir exatamente o mesmo enquadramento.
    readonly property real visualFocusX: flipX ? 1.0 - Math.max(0, Math.min(1, focusX)) : Math.max(0, Math.min(1, focusX))
    readonly property real visualFocusY: flipY ? 1.0 - Math.max(0, Math.min(1, focusY)) : Math.max(0, Math.min(1, focusY))

    clip: true

    Image {
        id: sourceImage
        objectName: "sceneImageSource"
        source: root.sourceUrl
        width: root.fit === "fill" ? root.width : root.naturalWidth * root.scaleValue
        height: root.fit === "fill" ? root.height : root.naturalHeight * root.scaleValue
        x: root.fit === "fill" ? 0 : (root.width - width) * root.visualFocusX
        y: root.fit === "fill" ? 0 : (root.height - height) * root.visualFocusY
        fillMode: Image.Stretch
        mirror: root.flipX
        mirrorVertically: root.flipY
        asynchronous: root.asynchronous
        cache: root.cache
        mipmap: root.mipmap
        smooth: root.smooth
    }
}
