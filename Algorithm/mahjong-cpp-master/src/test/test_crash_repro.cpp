#define CATCH_CONFIG_MAIN

#include <catch2/catch.hpp>

#include "server/json_parser.hpp"

TEST_CASE("repro crash payload from crawler log")
{
    const std::string json = R"(
        {
            "enable_reddora": true,
            "enable_uradora": true,
            "enable_shanten_down": true,
            "enable_tegawari": true,
            "enable_riichi": true,
            "round_wind": 27,
            "dora_indicators": [1],
            "hand": [35, 10, 1, 17, 21, 31, 25, 27, 20, 17, 17, 12, 27, 21],
            "melds": [],
            "seat_wind": 28,
            "wall": [4, 2, 4, 4, 4, 4, 4, 4, 3, 4, 3, 4, 3, 3, 4, 3, 3, 1, 3, 4, 2, 2, 4, 4, 4, 3, 4, 1, 4, 2, 4, 2, 2, 2, 1, 0, 1],
            "version": "0.9.1"
        }
    )";

    rapidjson::Document doc;
    parse_json(json, doc);
    Request req = parse_request_doc(doc);

    rapidjson::Document res_doc;
    res_doc.SetObject();
    rapidjson::Value response = create_response(req, res_doc);

    REQUIRE(response.IsObject());
    REQUIRE(response.HasMember("stats"));
    REQUIRE(response.HasMember("searched"));
}
