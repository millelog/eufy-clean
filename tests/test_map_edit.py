"""Map-edit commands (rename/merge/divide) encode the MapEditRequest the app sends."""

from base64 import b64decode

from google.protobuf.internal.decoder import _DecodeVarint

from custom_components.robovac_mqtt.api.commands import build_command
from custom_components.robovac_mqtt.api.map_stream import MapData, carpet_rects
from custom_components.robovac_mqtt.proto.cloud.common_pb2 import Floor, RoomScene
from custom_components.robovac_mqtt.proto.cloud.map_edit_pb2 import MapEditRequest


def _decode(cmd: dict) -> MapEditRequest:
    (raw,) = cmd.values()
    buf = b64decode(raw)
    n, pos = _DecodeVarint(buf, 0)
    return MapEditRequest.FromString(buf[pos : pos + n])


def test_rename_room():
    cmd = build_command("rename_room", map_id=4, room_id=2, name="Kitchen", floor="tile", scene="kitchen")
    assert list(cmd) == ["170"]
    req = _decode(cmd)
    assert req.method == MapEditRequest.RENAME_ROOM and req.map_id == 4
    assert req.room_desc.id == 2 and req.room_desc.name == "Kitchen"
    assert req.room_desc.floor.type == Floor.CERAMIC
    assert req.room_desc.scene.type == RoomScene.KITCHEN


def test_merge_and_divide():
    req = _decode(build_command("merge_rooms", map_id=4, room_ids=[1, 2]))
    assert req.method == MapEditRequest.MERGE_ROOMS and list(req.merge_rooms.room_ids) == [1, 2]
    req = _decode(build_command("divide_room", map_id=4, room_id=1, points_cm=[(-120, 40), (300, -15)]))
    assert req.method == MapEditRequest.DIVIDE_ROOM and req.divide_room.room_id == 1
    assert [(p.x, p.y) for p in req.divide_room.points] == [(-120, 40), (300, -15)]


def test_carpet_rects():
    w, h = 40, 20
    px = [2] * (w * h)  # free floor
    for y in range(2, 10):  # 10x8 rug at x 10..19, map rows 2..9 (image rows 10..17 after the Y-flip)
        for x in range(10, 20):
            px[y * w + x] = 3
    px[15 * w + 35] = 3  # a single noise pixel, ignored
    raw = bytes(sum(px[i + k] << (2 * k) for k in range(4)) for i in range(0, w * h, 4))
    assert carpet_rects(MapData(raw_pixels=raw, width=w, height=h)) == [(10 / w, 10 / h, 20 / w, 18 / h)]


if __name__ == "__main__":
    test_rename_room()
    test_merge_and_divide()
    test_carpet_rects()
    print("ok")
