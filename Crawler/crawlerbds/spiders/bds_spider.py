import re
import scrapy
from datetime import datetime
from urllib.parse import urljoin
from crawlerbds.items import BatdongsanItem


def _parse_post_date(raw):
    # Site dùng "yyyy/mm/dd" hoặc "yyyy-mm-dd"; tolerate cả hai.
    if not raw:
        return None
    s = str(raw).strip().replace("/", "-")
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


class BdsSpiderSpider(scrapy.Spider):
    name = "bds_spider"
    allowed_domains = ["bds.com.vn"]

    def __init__(
        self,
        min_page=-1,
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
        first_page_link = "https://bds.com.vn/mua-ban-nha-dat-{province}"
        page_link = "https://bds.com.vn/mua-ban-nha-dat-{province}-page{page_num}"
        if page_num == 1:
            return first_page_link.format_map(arg_map)
        else:
            return page_link.format_map(arg_map)

    def start_requests(self):
        domain_url = "https://bds.com.vn/"
        if self.estate_type == 0:
            start_url = domain_url + "mua-ban-nha-mat-pho"
        elif self.estate_type == 1:
            start_url = domain_url + "mua-ban-nha-rieng"
        elif self.estate_type == 2:
            start_url = domain_url + "mua-ban-can-ho-chung-cu"
        else:
            start_url = domain_url + "mua-ban-nha-biet-thu-lien-ke"
        yield scrapy.Request(url=start_url, callback=self.parse_home_page)

    def parse_home_page(self, response):

        province_page_links = response.css(
            "ul.list-menu-nhadat-service li h3 a::attr(href)"
        ).getall()

        for province_page_link in province_page_links:
            if self.estate_type == 0:
                province = province_page_link.split("/")[-1].replace(
                    "mua-ban-nha-mat-pho-", ""
                )
            elif self.estate_type == 1:
                province = province_page_link.split("/")[-1].replace(
                    "mua-ban-nha-rieng-", ""
                )
            elif self.estate_type == 2:
                province = province_page_link.split("/")[-1].replace(
                    "mua-ban-can-ho-chung-cu-", ""
                )
            else:
                province = province_page_link.split("/")[-1].replace(
                    "mua-ban-nha-biet-thu-lien-ke-", ""
                )
            if province == self.province:
                province_full_page_link = province_page_link
                if self.min_page > 1:
                    province_full_page_link += "-page" + str(self.min_page)
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
                real_estates = response.css("div.item-nhadat")
                for real_estate in real_estates:
                    real_estate_link = real_estate.css(
                        "a.title-item-nhadat::attr(href)"
                    ).get()
                    yield scrapy.Request(
                        url=real_estate_link,
                        callback=self.parse_real_estate_page,
                        meta={"province": province},
                    )

            if page == 1:
                next_pages = response.css(
                    "div.pagination.row-cl a.other-page::attr(href)"
                )
                next_page = next_pages[0].get() if next_pages else None
            else:
                next_page = response.css(
                    "div.pagination.row-cl a.next-page::attr(href)"
                ).get()
            if next_page is not None and page < self.max_page:
                next_page = urljoin("https://bds.com.vn/", next_page)
                yield scrapy.Request(
                    url=next_page,
                    callback=self.parse_province_page,
                    meta={"province": province, "page": page + 1},
                )

    # Diện tích hợp lý cho BĐS dân dụng VN. Bug đã gặp: trang có "5 Tầng" ở attr_items[1]
    # nên crawler lấy "5" gán vào square -> giá/m² bị nhân lệch hàng trăm lần.
    # Min=10 vì nhà mặt phố/đất không thể nhỏ hơn 10m² → bắt được case "5 tầng".
    _SQUARE_MIN_M2 = 10.0
    _SQUARE_MAX_M2 = 50000.0

    def _extract_square(self, attr_items, page_url):
        """Tìm diện tích theo LABEL trước; nếu không thấy thì fallback attr_items[1]
        kèm sanity check 5 <= sq <= 50000 m²."""
        # 1) Ưu tiên tìm theo label "Diện tích"
        for li in attr_items:
            li_text = " ".join(li.css("::text").getall()).lower()
            if "diện tích" in li_text or "dien tich" in li_text:
                val = li.css("span.value-attr::text").get()
                if val and self._is_valid_square_text(val):
                    return val
        # 2) Fallback: attr_items[1] như cũ NHƯNG validate
        if len(attr_items) > 1:
            candidate = attr_items[1].css("span.value-attr::text").get()
            if candidate and self._is_valid_square_text(candidate):
                return candidate
            if candidate:
                self.logger.warning(
                    "Square rejected (out of range or unparseable: %r) at %s",
                    candidate, page_url,
                )
        return None

    def _is_valid_square_text(self, raw):
        """Parse 'X m²' và kiểm tra hợp lý. True nếu giá trị nằm trong [5, 50000] m²."""
        if not raw:
            return False
        m = re.search(r"([\d.,]+)", raw)
        if not m:
            return False
        try:
            num = float(m.group(1).replace(",", "."))
        except ValueError:
            return False
        return self._SQUARE_MIN_M2 <= num <= self._SQUARE_MAX_M2

    def parse_real_estate_page(self, response):
        attr_hot = response.css("ul.list-attr-hot")
        if not attr_hot:
            self.logger.debug("Skip page (no list-attr-hot, likely 404): %s", response.url)
            return
        attr_items = attr_hot[0].css("li")
        if len(attr_items) < 2:
            self.logger.debug("Skip page (list-attr-hot has <2 items): %s", response.url)
            return

        bds_item = BatdongsanItem()

        bds_item["title"] = response.css("h1.title-product::text").get()
        bds_item["description"] = "\n".join(
            [line.strip() for line in response.css("div.ct-pr-sum::text").getall()]
        )
        bds_item["price"] = attr_items[0].css("span.value-attr::text").get()
        bds_item["square"] = self._extract_square(attr_items, response.url)
        bds_item["address"] = {
            "full_address": None,
            "province": None,
            "district": None,
            "ward": None,
        }
        bds_item["address"]["province"] = response.meta["province"]
        if response.css(".breadcrumb li").get() is not None:
            bds_item["address"]["full_address"] = ", ".join(
                [
                    add_info.strip()
                    for add_info in response.css(
                        "div.product_base ul.breadcrumb li a::text"
                    ).getall()[1:][::-1]
                ]
            )
        else:
            bds_item["address"]["full_address"] = None
        if self.estate_type == 0:
            bds_item["estate_type"] = "Nhà phố"
        elif self.estate_type == 1:
            bds_item["estate_type"] = "Nhà riêng"
        elif self.estate_type == 2:
            bds_item["estate_type"] = "Chung cư"
        else:
            bds_item["estate_type"] = "Biệt thự"
        bds_item["post_date"] = (
            response.css("ul.list-attr-hot")[0]
            .css("li")[2]
            .css("span.value-attr2::text")
            .get()
        )
        bds_item["post_id"] = (
            response.css("ul.list-attr-hot")[0]
            .css("li")[3]
            .css("span.value-attr2::text")
            .get()
        )

        contact_info = {}
        contact_info["name"] = response.css(
            "div.content-info-member span.member-name::text"
        ).get()
        phones = response.css(
            "div.row-contact-product a.hotline-member-detail ::attr(href)"
        ).getall()
        contact_info["phone"] = [phone.replace("tel:", "") for phone in phones]
        bds_item["contact_info"] = contact_info

        extra_infos = {}
        if response.css("ul.list-attr-hot")[1].css("li"):
            for extra_info in response.css("ul.list-attr-hot")[1].css("li"):
                label = extra_info.css("span::text").getall()[0]
                value = extra_info.css("span::text").getall()[1]
                extra_infos[label] = value

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
