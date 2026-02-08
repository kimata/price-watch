import { BuildingStorefrontIcon } from "@heroicons/react/24/outline";
import amazonIcon from "../assets/icons/amazon.svg";
import yodobashiIcon from "../assets/icons/yodobashi.svg";
import mercariIcon from "../assets/icons/mercari.svg";
import rakumaIcon from "../assets/icons/rakuma.svg";
import paypayIcon from "../assets/icons/paypay.svg";
import yahooIcon from "../assets/icons/yahoo.svg";
import rakutenIcon from "../assets/icons/rakuten.svg";

interface StoreIconProps {
    store: string;
    size?: number;
    className?: string;
}

// ストア名からアイコンへのマッピング
const STORE_ICONS: Record<string, string> = {
    Amazon: amazonIcon,
    ヨドバシ: yodobashiIcon,
    メルカリ: mercariIcon,
    ラクマ: rakumaIcon,
    PayPayフリマ: paypayIcon,
    Yahoo: yahooIcon,
    楽天: rakutenIcon,
};

export default function StoreIcon({ store, size = 16, className = "" }: StoreIconProps) {
    const icon = STORE_ICONS[store];

    if (icon) {
        return (
            <img
                src={icon}
                alt={store}
                width={size}
                height={size}
                className={`flex-shrink-0 ${className}`}
            />
        );
    }

    // 未知のストアはデフォルトアイコンを表示
    return (
        <BuildingStorefrontIcon
            className={`flex-shrink-0 ${className}`}
            style={{ width: size, height: size }}
        />
    );
}
