"""Master seed script — seed all cities and all data types into ChromaDB."""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CITY_SCRIPTS = {
    "chengdu": "seed_chengdu",
    "beijing": "seed_beijing",
    "shanghai": "seed_shanghai",
    "xian": "seed_xian",
}

TYPE_SCRIPTS = {
    "hotels": "seed_hotels",
    "restaurants": "seed_restaurants",
}

ALL_TYPES = {"attractions", "hotels", "restaurants"}


def seed_city(city: str):
    mod_name = CITY_SCRIPTS.get(city)
    if not mod_name:
        print(f"Unknown city: {city}. Available: {', '.join(CITY_SCRIPTS)}")
        return
    module = __import__(f"scripts.{mod_name}", fromlist=["seed"])
    module.seed()


def seed_type(data_type: str):
    mod_name = TYPE_SCRIPTS.get(data_type)
    if not mod_name:
        print(f"Unknown type: {data_type}. Available: {', '.join(TYPE_SCRIPTS)}")
        return
    module = __import__(f"scripts.{mod_name}", fromlist=["seed"])
    module.seed()


def seed_all():
    for city in CITY_SCRIPTS:
        try:
            seed_city(city)
        except Exception as e:
            print(f"Failed to seed attractions for {city}: {e}")

    for data_type in TYPE_SCRIPTS:
        try:
            seed_type(data_type)
        except Exception as e:
            print(f"Failed to seed {data_type}: {e}")


def show_counts():
    from app.services.chroma_store import get_chroma_store
    store = get_chroma_store()
    print(f"  Attractions: {store.collection_count('attractions')}")
    print(f"  Hotels:      {store.collection_count('hotels')}")
    print(f"  Restaurants: {store.collection_count('restaurants')}")


def clear_type(data_type: str):
    from app.services.chroma_store import get_chroma_store
    store = get_chroma_store()
    store.delete_collection(data_type)
    print(f"Cleared {data_type} collection.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed data into ChromaDB")
    parser.add_argument(
        "target",
        nargs="?",
        choices=list(CITY_SCRIPTS.keys()) + list(TYPE_SCRIPTS.keys()) + ["all"],
        default="all",
        help="City or data type to seed (default: all)",
    )
    parser.add_argument(
        "--clear",
        choices=sorted(ALL_TYPES) + ["all"],
        metavar="TYPE",
        help="Clear specific collection before seeding (attractions/hotels/restaurants/all)",
    )
    args = parser.parse_args()

    if args.clear:
        if args.clear == "all":
            for t in ALL_TYPES:
                clear_type(t)
        else:
            clear_type(args.clear)

    if args.target == "all":
        seed_all()
    elif args.target in CITY_SCRIPTS:
        seed_city(args.target)
    else:
        seed_type(args.target)

    show_counts()
