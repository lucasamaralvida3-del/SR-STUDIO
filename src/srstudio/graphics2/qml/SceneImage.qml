import QtQuick

Item {
    id: root

    property url sourceUrl: ""
    property string fit: "contain"
    property real imageZoom: 1.0
    property real focusX: 0.5
    property real focusY: 0.5
    property real cropLeft: 0.0
    property real cropTop: 0.0
    property real cropRight: 0.0
    property real cropBottom: 0.0
    property bool flipX: false
    property bool flipY: false
    property bool asynchronous: true
    property bool cache: true
    property bool mipmap: true
    property bool smooth: true

    function boundedCrop(value) {
        return Math.max(0, Math.min(0.98, Number(value || 0)))
    }

    readonly property real safeCropLeft: boundedCrop(cropLeft)
    readonly property real safeCropTop: boundedCrop(cropTop)
    readonly property real safeCropRight: Math.min(boundedCrop(cropRight), Math.max(0, 0.995 - safeCropLeft))
    readonly property real safeCropBottom: Math.min(boundedCrop(cropBottom), Math.max(0, 0.995 - safeCropTop))
    readonly property int status: sourceImage.status
    readonly property real sourceNaturalWidth: Math.max(1, Number(probeImage.implicitWidth || 1))
    readonly property real sourceNaturalHeight: Math.max(1, Number(probeImage.implicitHeight || 1))
    readonly property real naturalWidth: Math.max(1, sourceNaturalWidth * (1.0 - safeCropLeft - safeCropRight))
    readonly property real naturalHeight: Math.max(1, sourceNaturalHeight * (1.0 - safeCropTop - safeCropBottom))
    readonly property bool cropMode: fit === "cover" || imageZoom > 1.0001
    readonly property real baseScale: fit === "fill"
        ? 1.0
        : (cropMode
            ? Math.max(width / naturalWidth, height / naturalHeight)
            : Math.min(width / naturalWidth, height / naturalHeight))
    readonly property real scaleValue: fit === "fill" ? 1.0 : baseScale * (cropMode ? Math.max(0.05, imageZoom) : 1.0)
    readonly property real visualFocusX: flipX ? 1.0 - Math.max(0, Math.min(1, focusX)) : Math.max(0, Math.min(1, focusX))
    readonly property real visualFocusY: flipY ? 1.0 - Math.max(0, Math.min(1, focusY)) : Math.max(0, Math.min(1, focusY))

    clip: true

    Image {
        id: probeImage
        source: root.sourceUrl
        visible: false
        asynchronous: root.asynchronous
        cache: root.cache
    }

    Image {
        id: sourceImage
        objectName: "sceneImageSource"
        source: root.sourceUrl
        sourceClipRect: Qt.rect(
            root.sourceNaturalWidth * root.safeCropLeft,
            root.sourceNaturalHeight * root.safeCropTop,
            root.naturalWidth,
            root.naturalHeight
        )
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
