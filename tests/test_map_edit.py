"""Map-edit commands (rename/merge/divide) encode the MapEditRequest the app sends."""

from base64 import b64decode

from google.protobuf.internal.decoder import _DecodeVarint

from custom_components.robovac_mqtt.api.commands import build_command
from custom_components.robovac_mqtt.api.map_stream import MapData, carpet_rects, map_grid
from custom_components.robovac_mqtt.api.parser import update_state
from custom_components.robovac_mqtt.models import VacuumState
from custom_components.robovac_mqtt.proto.cloud.control_pb2 import ModeCtrlRequest
from custom_components.robovac_mqtt.proto.cloud.map_edit_pb2 import MapEditResponse
from custom_components.robovac_mqtt.proto.cloud.multi_maps_pb2 import MultiMapsManageRequest
from custom_components.robovac_mqtt.utils import encode_message
from custom_components.robovac_mqtt.proto.cloud.common_pb2 import Floor, RoomScene
from custom_components.robovac_mqtt.proto.cloud.map_edit_pb2 import MapEditRequest


def _decode(cmd: dict, msg=MapEditRequest):
    (raw,) = cmd.values()
    buf = b64decode(raw)
    n, pos = _DecodeVarint(buf, 0)
    return msg.FromString(buf[pos : pos + n])


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


def test_restricted_zones_order_rotate_reset():
    quad = [(0, 0), (100, 0), (100, 50), (0, 50)]
    req = _decode(build_command("set_restricted_zones", map_id=4, seq=7, virtual_walls=[((1, 2), (3, 4))],
                                forbidden_zones=[quad], ban_mop_zones=[quad, quad]))
    assert req.method == MapEditRequest.SET_RESTRICTED_ZONES and req.seq == 7
    rz = req.restricted_zone
    assert (rz.virtual_walls[0].p1.x, rz.virtual_walls[0].p1.y) == (3, 4)
    assert len(rz.forbidden_zones) == 1 and len(rz.ban_mop_zones) == 2 and rz.forbidden_zones[0].p2.x == 100
    req = _decode(build_command("set_room_order", map_id=4, room_ids=[3, 1]))
    assert [(r.id, r.order) for r in req.rooms_custom.rooms_order.rooms] == [(3, 1), (1, 2)]
    assert _decode(build_command("rotate_map", map_id=4, angle=450)).rotation.angle == 90
    assert _decode(build_command("reset_rooms", map_id=4)).method == MapEditRequest.RESET_ROOMS


def test_goto_and_multi_map():
    req = _decode(build_command("goto", x_cm=-50, y_cm=20, map_id=4, spot=True), ModeCtrlRequest)
    assert req.method == 4 and (req.go_to.destination.x, req.go_to.destination.y) == (-50, 20)
    assert req.go_to.type == req.go_to.GOTO_SPOT and req.go_to.map_id == 4
    req = _decode(build_command("map_rename", cloud_mapid=4, name="Home"), MultiMapsManageRequest)
    assert req.method == MultiMapsManageRequest.MAP_RENAME and req.rename.new_name == "Home"
    req = _decode(build_command("map_delete", cloud_mapid=5), MultiMapsManageRequest)
    assert req.method == MultiMapsManageRequest.MAP_DELETE and req.common.cloud_mapid == 5


def test_map_grid():
    w, h = 4, 2
    raw = bytes([2 | 2 << 2 | 1 << 4 | 3 << 6, 0])  # source row 0: free, free, wall, carpet; row 1 unknown
    # mask offset by one pixel (renderer's sign convention): grid x maps to mask x+1
    rooms = bytes([0, 0, 2 << 2, 61 << 2, 0, 0])
    md = MapData(raw_pixels=raw, width=w, height=h, room_pixels=rooms, room_outline_width=3,
                 room_outline_height=2, room_outline_origin_x=5)
    g = map_grid(md)
    assert g[:4] == bytes(4)  # top row = source row 1, all unknown
    assert list(g[4:]) == [2, 2 << 2 | 2, 1, 3]  # x1 room 2, x2 is id 61 -> 0, x3 outside mask


def test_map_edit_response_parsed():
    resp = MapEditResponse(method=MapEditRequest.DIVIDE_ROOM, seq=3, result=MapEditResponse.FAILED)
    resp.fail_code.value = MapEditResponse.FailCode.AREA_SMALL
    state, _ = update_state(VacuumState(), {"164": encode_message(resp)})
    assert state.last_map_edit == {"method": "divide_room", "seq": 3, "result": "failed", "fail_code": "area_small"}


if __name__ == "__main__":
    test_rename_room()
    test_merge_and_divide()
    test_carpet_rects()
    print("ok")
