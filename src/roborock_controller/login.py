from pathlib import Path

from roborock.web_api import RoborockApiClient

from roborock_controller.credentials import Credentials


async def login(email: str, secrets: Path) -> None:
    client = RoborockApiClient(username=email)
    await client.request_code_v4()
    code = input(f"Code sent to {email}: ").strip()
    user_data = await client.code_login_v4(code)
    credentials = Credentials(email, user_data, await client.base_url)
    credentials.save(secrets)
    print(f"Credentials written to {secrets}")

    home = await client.get_home_data_v3(user_data)
    products = {product.id: product for product in home.products}
    rooms = {room.id: room.name for room in home.rooms}
    for device in home.get_all_devices():
        product = products.get(device.product_id)
        print(f"\nDevice: {device.name} ({product.model if product else 'unknown model'}, protocol {device.pv})")
        print("Routines:")
        for scene in await client.get_scenes(user_data, device.duid):
            print(f"  {scene.id}: {scene.name}")
    print("\nRooms:")
    for room_id, name in rooms.items():
        print(f"  {room_id}: {name}")
