import React, { Children, Fragment, cloneElement, memo, useEffect, useState, useRef } from 'react';
import BookIcon from '@material-ui/icons/Book';
import { 
  Grid,  
  SvgIcon,
  Table,
  TableHead,
  TableCell,
  TableBody,
  TableRow 
} from '@mui/material'
import Chip from '@material-ui/core/Chip';
import { useMediaQuery, makeStyles, Button } from '@material-ui/core';
import lodashGet from 'lodash/get';
import jsonExport from 'jsonexport/dist';
import {
    BooleanField,
    BulkDeleteButton,
    BulkExportButton,
    ChipField,
    Datagrid,
    DateField,
    downloadCSV,
    EditButton,
    Filter,
    List,
    NumberField,
    ReferenceArrayField,
    SelectInput,
    Pagination,
    TopToolbar,
    SelectColumnsButton,    
    TextField,
    useRecordContext,
    RaRecord,
} from 'react-admin'; // eslint-disable-line import/no-unresolved

import ResetViewsButton from './ResetViewsButton';

import { useMap, Map, MapContainer, TileLayer, GeoJSON, LayersControl, Marker, Popup } from "react-leaflet";
import L from "leaflet";
// import "./styles.css";
import "leaflet/dist/leaflet.css";

export const PostIcon = BookIcon;

// 8 - tanker
const colors = ["fe4848", "fe6c58", "fe9068", "feb478", "fed686", "fed686", "fed686", "FF2D00"];

const useStyles = makeStyles(theme => ({
    title: {
        maxWidth: '20em',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
    },
    hiddenOnSmallScreens: {
        [theme.breakpoints.down('md')]: {
            display: 'none',
        },
    },
    publishedAt: { fontStyle: 'italic' },
}));

const position = [44.15615, 28.739, 12];

function handleOnFlyTo(setCoordinates, newPosition) {
  setCoordinates([newPosition[0],newPosition[1],newPosition[2]]);
  // const { current = {} } = mapRef;
  // const { leafletElement: map } = current;
  // const disneyLandLatLng = [33.8121, -117.9190];
  // map.flyTo(disneyLandLatLng, 14, {
  //   duration: 2
  // });
}

const Recalculate = ({startMoment, left, deltaRosouce}) => {
  const [currentCount, setCount] = useState();
  const ttt = () => {
    let curMoment = Date.now()
    let duration = Math.round((curMoment - startMoment)/1000)
    // console.log("DURATION", duration)
    setCount(Math.round(left+deltaRosouce*duration))
  };

  useEffect(
      () => {
          if (currentCount <= 0) {
              return;
          }
          const id = setInterval(ttt, 1000);
          return () => clearInterval(id);
      },[currentCount]);

  return <div>{currentCount}</div>
}

const RemeanResource = () => {
  // const [ value, setValue ] = useState(6000)

  // useEffect(() => {
  //     let aa = 4
  // }, [syncTimer]) 
  const record = useRecordContext();
  // record.substance.name
  const momentDate =  new Date(record.moment)
  const curYear = momentDate.getFullYear()
  const daysInYear = ((curYear % 4 === 0 && curYear % 100 > 0) || curYear %400 == 0) ? 366 : 365;
  const deltaResouce = record.final_total-record.initial_total
  const deltaRosoucePerDay = deltaResouce/daysInYear
  const curMoment = new Date()
  const deltaDuration = curMoment-momentDate
  const NumberOfaDay = Math.trunc(deltaDuration/(60*60*24*1000))
  const resDays =  record.initial_total + NumberOfaDay*deltaRosoucePerDay
  const deltaResoucePerSecond = deltaRosoucePerDay/24/60/60
  const dayStartMoment = new Date(curMoment.getFullYear(), curMoment.getMonth(), curMoment.getDate())
  const secondPassed = Math.trunc((curMoment-dayStartMoment)/1000)
  const resCurDay = secondPassed*deltaResoucePerSecond
  const resFull = resDays+resCurDay

  return <Recalculate
    left={resFull}
    startMoment={curMoment}
    deltaRosouce={deltaResoucePerSecond}
  />
}

RemeanResource.defaultProps = {
  label: 'Left substance',
  // source: 'rating',
};

const CustomField = ({setCoordnates, newPosition}) => {
  const record = useRecordContext();
  if (!record) return null;
  if (record.lat) return (<Button 
    variant="contained"
    size="small" 
    onClick={() => handleOnFlyTo(setCoordnates, [record.lat,record.lon])}>
      SHOW
      </Button>);
  return null;
    // <Chip
    //   // label={record.status}
    //   label="test"
    //   size="small"
    //   // color={
    //   //   record.status === "open"
    //   //     ? "primary"
    //   //     : record.status === "pending"
    //   //     ? "secondary"
    //   //     : "default"
    //   // }
    // />
}
  
const ExpandData = () => {
  const record = useRecordContext();

  // return <div>{record.total_to.map((item, index) => {
  //   return <div>
  //     <div>id: {item.id}</div>
  //     <div>value: {item.value}</div>
  //     <div>name: {item.substance_to.name}</div>
  //   </div>
  // })}</div>

  return (
    // <>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>
              Substance
            </TableCell>
            <TableCell>
              Value
            </TableCell>
            <TableCell>
              Substance
            </TableCell>
            <TableCell>
              Value
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
        {record.total_to.map((item, index) => {
          return <TableRow key={item.id}>
            <TableCell alig="right">
              <SvgIcon style = {{transform: 'rotate(0deg)' }}>
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={1.5}
                  stroke="currentColor"
                  color="red"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 1v9.263H1L12 23l11-12.737h-5.1V1H6Z"
                  />
                </svg>
              </SvgIcon>
                {"  "+record.substance.name}
            </TableCell>
            <TableCell>{item.value_to}</TableCell>
            <TableCell>
              <SvgIcon style = {{transform: 'rotate(180deg)' }}>
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={1.5}
                    stroke="currentColor"
                    color="green"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M6 1v9.263H1L12 23l11-12.737h-5.1V1H6Z"
                    />
                  </svg>
                </SvgIcon>
                  {"  "+item.substance_to.name}
              </TableCell>
              <TableCell>{item.value}</TableCell>
          </TableRow>
        })}
        </TableBody>
      </Table>

    // </>
  );

      // <div>{record.total_to.map((item, index) => {
      //   return <div>
      //     <div>id: {item.id}</div>
      //     <div>value: {item.value}</div>
      //     <div>name: {item.substance_to.name}</div>
      //   </div>
      // })}</div>


//   Table
//   TableHead
//   TableCell
//   TableCellRight
//   TableBody
//   TableRow
// <Table>
//             <TableHead>
//                 <TableRow>
//                     <TableCell>
//                         {translate(
//                             'resources.commands.fields.basket.reference'
//                         )}
//                     </TableCell>
//                     <TableCellRight>
//                         {translate(
//                             'resources.commands.fields.basket.unit_price'
//                         )}
//                     </TableCellRight>
//                     <TableCellRight>
//                         {translate('resources.commands.fields.basket.quantity')}
//                     </TableCellRight>
//                     <TableCellRight>
//                         {translate('resources.commands.fields.basket.total')}
//                     </TableCellRight>
//                 </TableRow>
//             </TableHead>
//             <TableBody>
//                 {record.basket.map((item: any) => (
//                     <TableRow key={item.product_id}>
//                         <TableCell>
//                             <Link to={`/products/${item.product_id}`}>
//                                 {productsById[item.product_id].reference}
//                             </Link>
//                         </TableCell>
//                         <TableCellRight>
//                             {productsById[item.product_id].price.toLocaleString(
//                                 undefined,
//                                 {
//                                     style: 'currency',
//                                     currency: 'USD',
//                                 }
//                             )}
//                         </TableCellRight>
//                         <TableCellRight>{item.quantity}</TableCellRight>
//                         <TableCellRight>
//                             {(
//                                 productsById[item.product_id].price *
//                                 item.quantity
//                             ).toLocaleString(undefined, {
//                                 style: 'currency',
//                                 currency: 'USD',
//                             })}
//                         </TableCellRight>
//                     </TableRow>
//                 ))}
//             </TableBody>
//         </Table>
//     );



}


const ShipList = props => {
    // const map = useMap();

  // const [selected, setSelected] = useState();

  //   function handleItemClick(index) {
  //     console.log(index)
  //     setSelected(8);
  //   }

  // const [currentCount, setCount] = useState(100);
  // const ttt = () => {
  //   console.log("EVENT", currentCount)
  //   setCount(currentCount - 1)
  // };

  // useEffect(
  //     () => {
  //         if (currentCount <= 0) {
  //             return;
  //         }
  //         const id = setInterval(ttt, 1000);
  //         return () => clearInterval(id);
  //     },[currentCount]);


  function newEvent() {
    setSyncTimer(Date.now())
    console.log("new event")
  }

  const [ syncTimer, setSyncTimer ] = useState(Date.now());
  const [ timer, setTimer ] = useState(null);
  // useEffect(() => {
  //   let tt = setInterval(newEvent(), 10000)
  //   return () => clearInterval(tt);
  // }, [syncTimer])

    const [ coordinates, setCoordnates ] = useState(position);

    const classes = useStyles();
    const isSmall = useMediaQuery(theme => theme.breakpoints.down('sm'));

    // const [pointsShow, setPointsShow] = useState([])

    // useEffect(() => {
    //     fetchDataReal(setPointsShow, position[0], position[1], 8)
    // },[])
  
    return (
        <Grid container aligment="stretch" spacing={1}>
            <Grid item md={12}>
                <List
                    actions={null}
                    // actions={<ListActions/>}
                    bulkActionButtons={false}
                    perPage={15}
                    pagination={<Pagination  rowsPerPageOptions={[10, 15, 20]} />}
                    {...props}
                >
                    <Datagrid 
                      optimized
                      expand={<ExpandData/>}
                      >
                        <TextField source="id" />
                        <TextField label="Substance" source="substance.name" />
                        {/* <TextField source="initial_total" cellClassName={classes.initial_total} /> */}
                        <RemeanResource/>
                        {/* <TextField source="flag" cellClassName={classes.flag} />
                        <ShipTypeField /> */}
                        {/* <TextField source="type" cellClassName={classes.type} /> */}
                        {/* <TextField source="lat" cellClassName={classes.lat} />
                        <TextField source="lon" cellClassName={classes.lon} /> */}
                        {/* <CustomField setCoordnates={setCoordnates} newPosition={newPosition}/> */}
                    </Datagrid>
                </List>
            </Grid>
        </Grid>
    );
};

export default ShipList;
