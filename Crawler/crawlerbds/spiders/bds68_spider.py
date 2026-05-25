from typing import Iterable
import scrapy
from urllib.parse import urljoin
from scrapy.http import Request
from datetime import date, datetime, timedelta
from crawlerbds.items import BatdongsanItem
import re


def _parse_post_date(raw):
    # Site dùng "yyyy/mm/dd" hoặc "yyyy-mm-dd"; tolerate cả hai.
    if not raw:
        return None
    s = str(raw).strip().replace("/", "-")
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


class IBatdongsanSpider(scrapy.Spider):
    name = "bds68_spider"
    allowed_domains = ["bds68.com.vn"]

    def __init__(
        self,
        min_page=1,
        max_page=999999,
        province="ha-noi",
        jump_to_page=-1,
        estate_type=0,
        min_date="2025-01-01",
    ):
        super().__init__()
        self.min_page = int(min_page)
        self.max_page = int(max_page)
        self.province = province
        self.jump_to_page = int(jump_to_page)
        self.estate_type = int(estate_type)
        self.min_date = _parse_post_date(min_date) if min_date else None

    def _get_page_url(self, province, page_num):
        arg_map = {"province": province, "page_num": page_num}
        first_page_link = "https://i-batdongsan.com/can-ban-nha-dat/{province}-t1.htm"
        page_link = (
            "https://i-batdongsan.com/can-ban-nha-dat/{province}-t1/p{page_num}.htm"
        )
        if page_num == 1:
            return first_page_link.format_map(arg_map)
        else:
            return page_link.format_map(arg_map)

    def start_requests(self):
        domain_url = "https://bds68.com.vn/"
        if self.estate_type == 0:
            start_url = domain_url + "ban-nha-mat-tien/"
        elif self.estate_type == 1:
            start_url = domain_url + "ban-nha-rieng/"
        elif self.estate_type == 2:
            start_url = domain_url + "ban-chung-cu/"
        elif self.estate_type == 3:
            start_url = domain_url + "ban-nha-biet-thu-du-an/"
        elif self.estate_type == 4:
            start_url = domain_url + "ban-dat-biet-thu-du-an/"
        elif self.estate_type == 5:
            start_url = domain_url + "ban-dat-mat-tien/"
        elif self.estate_type == 6:
            start_url = domain_url + "ban-dat/"
        elif self.estate_type == 7:
            start_url = domain_url + "ban-dat-trang-trai/"
        elif self.estate_type == 8:
            start_url = domain_url + "ban-kho-nha-xuong/"
        elif self.estate_type == 9:
            start_url = domain_url + "nha-dat-ban-khac/"
        elif self.estate_type == 10:
            start_url = domain_url + "thue-chung-cu/"
        elif self.estate_type == 11:
            start_url = domain_url + "thue-nha-rieng/"
        elif self.estate_type == 12:
            start_url = domain_url + "thue-nha-mat-tien/"
        elif self.estate_type == 13:
            start_url = domain_url + "thue-van-phong/"
        elif self.estate_type == 14:
            start_url = domain_url + "thue-cua-hang-kiot/"
        elif self.estate_type == 15:
            start_url = domain_url + "thue-kho-xuong/"
        elif self.estate_type == 16:
            start_url = domain_url + "thue-nha-tro/"
        elif self.estate_type == 17:
            start_url = domain_url + "cho-thue-khac/"
        yield scrapy.Request(url=start_url, callback=self.parse_home_page)

    def parse_home_page(self, response):

        province_page_links = response.css(
            "div.readmore-box ul li a::attr(href)"
        ).getall()

        for province_page_link in province_page_links:
            province = province_page_link.split("/")[-1]
            if province == self.province:
                province_full_page_link = (
                    urljoin("https://bds68.com.vn/", province_page_link) + "?sx=1"
                    if self.min_page == 1
                    else urljoin("https://bds68.com.vn/", province_page_link)
                    + "?sx=1&pg="
                    + str(self.min_page)
                )
                yield scrapy.Request(
                    url=province_full_page_link,
                    callback=self.parse_province_page,
                    meta={"province": province, "page": self.min_page},
                )

    def parse_province_page(self, response):
        province = response.meta["province"]
        page = response.meta["page"]

        if self.jump_to_page > 1:
            dest_page_num = self.jump_to_page
            self.jump_to_page = -1
            yield scrapy.Request(
                url=self._get_page_url(province=province, page_num=dest_page_num),
                callback=self.parse_province_page,
                meta={"province": province, "page": dest_page_num},
            )
        else:
            if page >= self.min_page:
                real_estates = response.css(
                    "div.prop-box-item-contain div div.div_prop_wapper.clearfix"
                )
                for real_estate in real_estates:
                    real_estate_link = real_estate.css(
                        "div.div_prop_info div h4 a::attr(href)"
                    ).get()
                    real_estate_link = urljoin(
                        "https://bds68.com.vn/", real_estate_link
                    )
                    yield scrapy.Request(
                        url=real_estate_link,
                        callback=self.parse_real_estate_page,
                        meta={"province": province},
                    )

            page_links = response.css(
                "div.paging div div div ul li a::attr(href)"
            ).getall()[1:-1]
            page_numbers = [page_link.split("pg=")[-1] for page_link in page_links]
            current_page = response.css(
                "div.paging div div div ul li.active span::text"
            ).get()
            if not current_page or not page_numbers:
                next_page = None
            else:
                if int(current_page) == 1:
                    current_page_idx = 0
                else:
                    current_page_idx = int(current_page) - int(page_numbers[0])
                if current_page_idx >= len(page_links):
                    next_page = None
                else:
                    next_page = page_links[current_page_idx]
                if next_page is not None and page < self.max_page:
                    next_page = urljoin("https://bds68.com.vn/", next_page)
                    yield scrapy.Request(
                        url=next_page,
                        callback=self.parse_province_page,
                        meta={"province": province, "page": page + 1},
                    )

    def parse_real_estate_page(self, response):
        bds_item = BatdongsanItem()

        bds_item["title"] = response.css("h1.detail-prop-title ::text").get()
        bds_item["description"] = response.css("div.prop-description div p::text").get()
        bds_item["address"] = {
            "full_address": None,
            "province": None,
            "district": None,
            "ward": None,
        }
        bds_item["address"]["province"] = response.meta["province"]
        bds_item["address"]["full_address"] = response.css(
            "div.prop-address a span::text"
        ).get()

        contact_info = {}
        contact_info["name"] = response.css(
            "div.seller-info-container a div.seller-info-header div h3::text"
        ).get()

        ## Lấy SĐT
        # Selector nhắm thẳng vào text node của span.hide-phone
        selector_path = (
            "a.phone-link div.seller-info-phone div.infoPhone span.hide-phone ::text"
        )
        contact_info["phone"] = [response.css(selector_path).get().strip()]

        bds_item["contact_info"] = contact_info

        extra_infos = {}
        info_rows = response.css("div.prop-features div::text").getall()
        for row in range(3, len(info_rows)):
            row_info = info_rows[row]
            parts = row_info.split(":")
            if len(parts) != 2:
                continue
            if "Nội thất" in parts[0] or "nội thất" in parts[0]:
                continue
            if self.estate_type == 0:
                bds_item["estate_type"] = "Nhà phố"
            elif self.estate_type == 1:
                bds_item["estate_type"] = "Nhà riêng"
            elif self.estate_type == 2:
                bds_item["estate_type"] = "Chung cư"
            elif self.estate_type == 3:
                bds_item["estate_type"] = "Biệt thự"
            elif self.estate_type == 4:
                bds_item["estate_type"] = "Đất biệt thự"
            elif self.estate_type == 5:
                bds_item["estate_type"] = "Đất mặt tiền"
            elif self.estate_type == 6:
                bds_item["estate_type"] = "Đất"
            elif self.estate_type == 7:
                bds_item["estate_type"] = "Đất trang trại"
            elif self.estate_type == 8:
                bds_item["estate_type"] = "Kho xưởng"
            elif self.estate_type == 9:
                bds_item["estate_type"] = "Nhà đất khác"
            elif self.estate_type == 10:
                bds_item["estate_type"] = "Chung cư cho thuê"
            elif self.estate_type == 11:
                bds_item["estate_type"] = "Nhà riêng cho thuê"
            elif self.estate_type == 12:
                bds_item["estate_type"] = "Nhà mặt tiền cho thuê"
            elif self.estate_type == 13:
                bds_item["estate_type"] = "Văn phòng cho thuê"
            elif self.estate_type == 14:
                bds_item["estate_type"] = "Cửa hàng cho thuê"
            elif self.estate_type == 15:
                bds_item["estate_type"] = "Kho xưởng cho thuê"
            elif self.estate_type == 16:
                bds_item["estate_type"] = "Nhà trọ cho thuê"
            elif self.estate_type == 17:
                bds_item["estate_type"] = "Bất động sản cho thuê khác"
            else:
                bds_item["estate_type"] = ""

            if re.sub(r"\s+", " ", parts[0]).strip() == "Giá":
                bds_item["price"] = re.sub(r"\s+", " ", parts[1]).strip()
            elif re.sub(r"\s+", " ", parts[0]).strip() == "Diện Tích":
                bds_item["square"] = re.sub(r"\s+", " ", parts[1]).strip()
            elif re.sub(r"\s+", " ", parts[0]).strip() == "Mã Đăng Tin":
                bds_item["post_id"] = re.sub(r"\s+", " ", parts[1]).strip()
            elif re.sub(r"\s+", " ", parts[0]).strip() == "Ngày Đăng":
                bds_item["post_date"] = (
                    re.sub(r"\s+", " ", parts[1]).split("-")[0].strip()
                )
            else:
                extra_infos[re.sub(r"\s+", " ", parts[0]).strip()] = re.sub(
                    r"\s+", " ", parts[1]
                ).strip()

        bds_item["extra_infos"] = extra_infos

        bds_item["link"] = response.url

        if self.min_date:
            post_dt = _parse_post_date(bds_item.get("post_date"))
            if post_dt and post_dt < self.min_date:
                self.logger.debug(
                    "Skip post %s (post_date=%s < min_date=%s)",
                    bds_item.get("post_id"),
                    bds_item.get("post_date"),
                    self.min_date,
                )
                return

        yield bds_item
