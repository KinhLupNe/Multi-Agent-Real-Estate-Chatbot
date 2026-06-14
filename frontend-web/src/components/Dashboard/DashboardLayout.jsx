import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { MapContainer, TileLayer, CircleMarker, Tooltip as LeafletTooltip } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import './Dashboard.css';

// Using raw JSON for coordinates (ensure it was copied to src directory)
import districtCoords from '../../district_coords_full.json';

const PROVINCES_LIST = [
  "An Giang", "Bà Rịa - Vũng Tàu", "Bắc Giang", "Bắc Kạn", "Bạc Liêu",
  "Bắc Ninh", "Bến Tre", "Bình Định", "Bình Dương", "Bình Phước",
  "Bình Thuận", "Cà Mau", "Cần Thơ", "Cao Bằng", "Đà Nẵng",
  "Đắk Lắk", "Đắk Nông", "Điện Biên", "Đồng Nai", "Đồng Tháp",
  "Gia Lai", "Hà Giang", "Hà Nam", "Hà Nội", "Hà Tĩnh",
  "Hải Dương", "Hải Phòng", "Hậu Giang", "Hòa Bình", "TP. Hồ Chí Minh",
  "Hưng Yên", "Khánh Hòa", "Kiên Giang", "Kon Tum", "Lai Châu",
  "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Long An", "Nam Định",
  "Nghệ An", "Ninh Bình", "Ninh Thuận", "Phú Thọ", "Phú Yên",
  "Quảng Bình", "Quảng Nam", "Quảng Ngãi", "Quảng Ninh", "Quảng Trị",
  "Sóc Trăng", "Sơn La", "Tây Ninh", "Thái Bình", "Thái Nguyên",
  "Thanh Hóa", "Thừa Thiên Huế", "Tiền Giang", "Trà Vinh", "Tuyên Quang",
  "Vĩnh Long", "Vĩnh Phúc", "Yên Bái"
];

const ESTATE_TYPES = ["Nhà mặt tiền", "Nhà riêng", "Chung cư", "Biệt thự", "Đất"];
const ESTATE_TYPE_INDEX_MAP = {
  "Nhà mặt tiền": "nhamatpho",
  "Nhà riêng": "nharieng",
  "Chung cư": "chungcu",
  "Biệt thự": "bietthu",
  "Đất": "dat"
};

const COLORS = ['#89b4fa', '#a6e3a1', '#fab387', '#cba6f7', '#f38ba8', '#f9e2af'];

export default function DashboardLayout() {
  const [province, setProvince] = useState("Hà Nội");
  const [estateType, setEstateType] = useState("Nhà mặt tiền");
  
  const [kpi, setKpi] = useState({ total_listings: 0, median_price: 0, median_price_per_sq: 0 });
  const [priceByDistrict, setPriceByDistrict] = useState([]);
  const [pricePerSqByDistrict, setPricePerSqByDistrict] = useState([]);
  const [segments, setSegments] = useState([]);

  useEffect(() => {
    fetchData();
  }, [province, estateType]);

  const fetchData = async () => {
    try {
      // 1. Set active province
      await axios.post(`/set_active_province/${province}`);
      
      const typeIndex = ESTATE_TYPE_INDEX_MAP[estateType];
      
      // 2. Fetch KPI
      const kpiRes = await axios.get(`/dashboard/kpi/buy/${typeIndex}`);
      setKpi(kpiRes.data);

      // 3. Fetch Prices by District
      const priceRes = await axios.get(`/get_price_by_district/buy/${typeIndex}`);
      const formattedPrices = priceRes.data.districts.map((d, i) => ({
        name: d,
        value: priceRes.data.avg_prices[i]
      }));
      setPriceByDistrict(formattedPrices);

      // 4. Fetch Price per Sq by District
      const ppsRes = await axios.get(`/get_price_per_square_by_district/buy/${typeIndex}`);
      const formattedPps = ppsRes.data.districts.map((d, i) => ({
        name: d,
        value: ppsRes.data.avg_prices_per_square[i]
      }));
      setPricePerSqByDistrict(formattedPps);

      // 5. Fetch Segments
      const segRes = await axios.get(`/dashboard/price_segments/buy/${typeIndex}`);
      setSegments(segRes.data.segments);
    } catch (e) {
      console.error("Failed to fetch dashboard data", e);
    }
  };

  const fmtVND = (val) => {
    if (!val) return "—";
    if (val >= 1e9) return `${(val / 1e9).toFixed(1)} tỷ`;
    if (val >= 1e6) return `${(val / 1e6).toFixed(0)} triệu`;
    return val.toLocaleString();
  };

  // Map logic
  const mapCenter = [21.0285, 105.8542];
  const mapData = priceByDistrict.map(item => {
    const coords = districtCoords[province]?.[item.name];
    if (!coords) return null;
    return { ...item, coords };
  }).filter(Boolean);

  if (mapData.length > 0) {
    const lats = mapData.map(d => d.coords[0]);
    const lons = mapData.map(d => d.coords[1]);
    mapCenter[0] = lats.reduce((a, b) => a + b, 0) / lats.length;
    mapCenter[1] = lons.reduce((a, b) => a + b, 0) / lons.length;
  }

  return (
    <div className="dashboard-container animate-fade-in">
      <div className="dashboard-header">
        <div className="dashboard-select-group">
          <label>Tỉnh/Thành phố</label>
          <select value={province} onChange={(e) => setProvince(e.target.value)}>
            {PROVINCES_LIST.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="dashboard-select-group">
          <label>Loại bất động sản</label>
          <select value={estateType} onChange={(e) => setEstateType(e.target.value)}>
            {ESTATE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      </div>

      <div className="dashboard-kpi-grid">
        <div className="kpi-card glass-panel">
          <div className="kpi-label">🏘️ Tổng tin đăng</div>
          <div className="kpi-value">{kpi.total_listings.toLocaleString()}</div>
        </div>
        <div className="kpi-card glass-panel">
          <div className="kpi-label">💰 Giá điển hình</div>
          <div className="kpi-value">{fmtVND(kpi.median_price)}</div>
        </div>
        <div className="kpi-card glass-panel">
          <div className="kpi-label">📐 Giá/m² điển hình</div>
          <div className="kpi-value">{fmtVND(kpi.median_price_per_sq)}</div>
        </div>
      </div>

      <div className="dashboard-section">
        <h3 className="dashboard-section-title">Giá theo quận/huyện</h3>
        <div className="charts-grid">
          <div className="chart-card glass-panel">
            <h4 className="chart-title">Giá Trung Bình (VNĐ)</h4>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={priceByDistrict}>
                <XAxis dataKey="name" tick={{fill: 'var(--text-secondary)'}} angle={-45} textAnchor="end" height={80} />
                <YAxis tick={{fill: 'var(--text-secondary)'}} tickFormatter={(val) => `${val/1e9}T`} />
                <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{background: 'var(--bg-surface)', border: '1px solid var(--border)'}} />
                <Bar dataKey="value" fill="var(--primary)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          
          <div className="chart-card glass-panel">
            <h4 className="chart-title">Giá/m² Trung Bình (VNĐ)</h4>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={pricePerSqByDistrict}>
                <XAxis dataKey="name" tick={{fill: 'var(--text-secondary)'}} angle={-45} textAnchor="end" height={80} />
                <YAxis tick={{fill: 'var(--text-secondary)'}} tickFormatter={(val) => `${val/1e6}Tr`} />
                <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{background: 'var(--bg-surface)', border: '1px solid var(--border)'}} />
                <Bar dataKey="value" fill="var(--accent-green)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="dashboard-section">
        <h3 className="dashboard-section-title">Phân phối phân khúc giá</h3>
        <div className="chart-card glass-panel" style={{ height: '400px' }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={segments} layout="vertical">
              <XAxis type="number" tick={{fill: 'var(--text-secondary)'}} />
              <YAxis dataKey="label" type="category" width={150} tick={{fill: 'var(--text-secondary)'}} />
              <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{background: 'var(--bg-surface)', border: '1px solid var(--border)'}} />
              <Bar dataKey="count" fill="var(--accent-peach)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="dashboard-section">
        <h3 className="dashboard-section-title">Bản đồ nhiệt — {estateType} tại {province}</h3>
        <div className="glass-panel map-container">
          <MapContainer center={mapCenter} zoom={10} style={{ height: '100%', width: '100%', background: 'var(--bg-surface-alt)' }}>
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
            />
            {mapData.map((data, idx) => (
              <CircleMarker
                key={idx}
                center={data.coords}
                radius={8}
                pathOptions={{
                  fillColor: 'var(--accent-red)',
                  fillOpacity: 0.7,
                  color: 'white',
                  weight: 1
                }}
              >
                <LeafletTooltip>
                  {data.name}: {fmtVND(data.value)}
                </LeafletTooltip>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>
      </div>
    </div>
  );
}
